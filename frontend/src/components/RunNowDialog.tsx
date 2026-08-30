import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiClient } from "@/api-platform";
import { webPlatformPolicy } from "@/lib/webPlatformPolicy";
import type { RunCreate } from "@/types-platform";
import type { WorkflowParameter } from "@/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  buildParameterDefaults,
  ParameterFormFields,
  parseParameterValues,
} from "./ParameterFormFields";

interface Props {
  open: boolean;
  onOpenChange(open: boolean): void;
  workflowId: string;
  parameters: WorkflowParameter[];
  onSubmit(body: RunCreate): void;
  submitting?: boolean;
}

export function RunNowDialog({
  open,
  onOpenChange,
  workflowId,
  parameters,
  onSubmit,
  submitting,
}: Props) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [browserProfileId, setBrowserProfileId] = useState<string>("");
  const [browserSessionId, setBrowserSessionId] = useState<string>("");
  const [executionMode, setExecutionMode] = useState<"cloud" | "worker">("cloud");
  const [workerPool, setWorkerPool] = useState("default");
  const [workerId, setWorkerId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const runtimeQuery = useQuery({
    queryKey: ["settings", "runtime"],
    queryFn: () => apiClient.settings.runtime(),
    enabled: open,
    staleTime: 60_000,
  });
  const workerOnly = runtimeQuery.data?.worker_only ?? false;
  const showBrowserOptions =
    webPlatformPolicy.showBrowserSessions || webPlatformPolicy.showBrowserProfiles;

  const profilesQuery = useQuery({
    queryKey: ["browser-profiles"],
    queryFn: () => apiClient.browserProfiles.list(),
    enabled: open && showBrowserOptions && webPlatformPolicy.showBrowserProfiles,
  });

  const sessionsQuery = useQuery({
    queryKey: ["browser-sessions"],
    queryFn: () => apiClient.browserSessions.list(),
    enabled: open && showBrowserOptions && webPlatformPolicy.showBrowserSessions,
    refetchInterval: open ? 15_000 : false,
  });

  const workersQuery = useQuery({
    queryKey: ["workers"],
    queryFn: () => apiClient.workers.list(),
    enabled: open && executionMode === "worker",
    refetchInterval: open && executionMode === "worker" ? 10_000 : false,
  });

  useEffect(() => {
    if (open) {
      setValues(buildParameterDefaults(parameters));
      setBrowserProfileId("");
      setBrowserSessionId("");
      setExecutionMode(workerOnly ? "worker" : "cloud");
      setWorkerPool("default");
      setWorkerId("");
      setError(null);
    }
  }, [open, parameters, workerOnly]);

  async function handleSubmit() {
    try {
      const parsed = parseParameterValues(parameters, values);
      for (const param of parameters) {
        if (param.required) {
          const val = parsed[param.name];
          if (param.type === "file") {
            const hasFile =
              val &&
              typeof val === "object" &&
              ("file_id" in (val as object) || "file" in (val as object));
            if (!hasFile) {
              setError(
                t("runDialog.requiredField", { name: param.label || param.name }),
              );
              return;
            }
            continue;
          }
          if (val === undefined || val === null || val === "") {
            setError(
              t("runDialog.requiredField", { name: param.label || param.name }),
            );
            return;
          }
        }
      }

      setUploading(true);
      const resolvedParams = { ...parsed };
      for (const param of parameters) {
        if (param.type !== "file") continue;
        const val = resolvedParams[param.name];
        if (!val || typeof val !== "object" || !("file" in val)) continue;
        const picked = (val as { file?: File }).file;
        if (!picked) continue;
        const staged = await apiClient.workflows.uploadInputFile(
          workflowId,
          picked,
        );
        resolvedParams[param.name] = { file_id: staged.file_id };
      }

      const body: RunCreate = {};
      if (Object.keys(resolvedParams).length > 0) {
        body.parameters = resolvedParams;
      }
      if (browserProfileId) {
        body.browser_profile_id = browserProfileId;
      }
      if (browserSessionId && executionMode === "cloud") {
        body.browser_session_id = browserSessionId;
      }
      body.execution_mode = executionMode;
      if (executionMode === "worker") {
        body.worker_pool = workerPool || "default";
        if (workerId) {
          body.worker_id = workerId;
        }
      }
      onSubmit(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  const profiles = profilesQuery.data ?? [];
  const liveSessions = (sessionsQuery.data ?? []).filter(
    (s) => s.status === "live" || s.status === "idle",
  );
  const onlineWorkers = (workersQuery.data ?? []).filter(
    (w) => w.status === "online" && !w.revoked_at,
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("runDialog.title")}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
            <div>
              <Label htmlFor="execution-mode">{t("runDialog.executionMode")}</Label>
              <p className="text-xs text-muted-foreground">
                {executionMode === "worker"
                  ? t("runDialog.executionModeWorkerHint")
                  : t("runDialog.executionModeCloudHint")}
              </p>
            </div>
            {!workerOnly && (
              <Switch
                id="execution-mode"
                checked={executionMode === "worker"}
                onCheckedChange={(checked) =>
                  setExecutionMode(checked ? "worker" : "cloud")
                }
                disabled={submitting || uploading}
              />
            )}
            {workerOnly && (
              <span className="text-xs font-medium text-muted-foreground">
                {t("runDialog.executionModeWorkerOnly")}
              </span>
            )}
          </div>

          {executionMode === "worker" && (
            <>
              <div className="flex flex-col gap-1">
                <Label>{t("runDialog.workerPool")}</Label>
                <Select value={workerPool} onValueChange={setWorkerPool}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">default</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label>{t("runDialog.workerPin")}</Label>
                <Select
                  value={workerId || "__any__"}
                  onValueChange={(v) => setWorkerId(v === "__any__" ? "" : v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t("runDialog.workerPinAny")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__any__">
                      {t("runDialog.workerPinAny")}
                    </SelectItem>
                    {onlineWorkers.map((w) => (
                      <SelectItem key={w.id} value={w.id}>
                        {w.display_name || w.hostname} ({w.environment_status})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          {executionMode === "cloud" &&
            webPlatformPolicy.showBrowserSessions &&
            liveSessions.length > 0 && (
            <div className="flex flex-col gap-1">
              <Label>{t("runDialog.browserSession")}</Label>
              <Select
                value={browserSessionId || "__none__"}
                onValueChange={(v) =>
                  setBrowserSessionId(v === "__none__" ? "" : v)
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("runDialog.browserSessionNone")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">
                    {t("runDialog.browserSessionNone")}
                  </SelectItem>
                  {liveSessions.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.id.slice(0, 8)}… ({t(`browserSessions.status.${s.status}`)})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {webPlatformPolicy.showBrowserProfiles && profiles.length > 0 && (
            <div className="flex flex-col gap-1">
              <Label>{t("runDialog.browserProfile")}</Label>
              <Select
                value={browserProfileId || "__none__"}
                onValueChange={(v) =>
                  setBrowserProfileId(v === "__none__" ? "" : v)
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("runDialog.browserProfileNone")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">
                    {t("runDialog.browserProfileNone")}
                  </SelectItem>
                  {profiles.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <ParameterFormFields
            parameters={parameters}
            values={values}
            onChange={(name, value) =>
              setValues((prev) => ({ ...prev, [name]: value }))
            }
            disabled={submitting || uploading}
          />

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting || uploading}
          >
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || uploading}>
            {submitting || uploading
              ? t("runDialog.starting")
              : t("runDialog.startRun")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
