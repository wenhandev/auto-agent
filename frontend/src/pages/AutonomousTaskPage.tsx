import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, Play } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import { routePath } from "@/routes";
import type { TaskCreate } from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { mergeDesktopAllowedTools } from "@/lib/desktopTools";

export function AutonomousTaskPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [objective, setObjective] = useState("");
  const [startUrl, setStartUrl] = useState("");
  const [maxSteps, setMaxSteps] = useState("30");
  const [maxSeconds, setMaxSeconds] = useState("300");
  const [successCriteria, setSuccessCriteria] = useState("");
  const [requireConfirmation, setRequireConfirmation] = useState(false);
  const [enableDesktopTools, setEnableDesktopTools] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runtimeQuery = useQuery({
    queryKey: ["settings", "runtime"],
    queryFn: () => apiClient.settings.runtime(),
    staleTime: 60_000,
  });
  const workerOnly = runtimeQuery.data?.worker_only ?? false;

  const createMut = useMutation({
    mutationFn: (body: TaskCreate) => apiClient.tasks.create(body),
    onSuccess: (task) => {
      navigate(routePath.runReplay(task.id));
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
          : err instanceof Error
            ? err.message
            : String(err);
      setError(message);
    },
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!objective.trim()) {
      setError(t("tasks.objectiveRequired"));
      return;
    }
    setError(null);
    const body: TaskCreate = {
      objective: objective.trim(),
      require_confirmation: requireConfirmation,
      synthesize_workflow: false,
    };
    if (startUrl.trim()) body.start_url = startUrl.trim();
    const steps = Number(maxSteps);
    if (!Number.isNaN(steps) && steps > 0) body.max_steps = steps;
    const seconds = Number(maxSeconds);
    if (!Number.isNaN(seconds) && seconds > 0) body.max_seconds = seconds;
    if (successCriteria.trim()) {
      body.success_criteria = successCriteria.trim();
    }
    if (enableDesktopTools) {
      body.allowed_tools = mergeDesktopAllowedTools(Boolean(startUrl.trim()));
    }
    if (workerOnly) {
      body.execution_mode = "worker";
    }
    createMut.mutate(body);
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="border-b bg-card/40 px-6 py-4">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary" />
          <div>
            <h1 className="text-lg font-semibold">{t("tasks.title")}</h1>
            <p className="text-sm text-muted-foreground">{t("tasks.subtitle")}</p>
          </div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-2xl p-6">
        <Card>
          <CardHeader>
            <CardTitle>{t("tasks.formTitle")}</CardTitle>
            <CardDescription>{t("tasks.formDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="objective">{t("tasks.objectiveLabel")}</Label>
                <Textarea
                  id="objective"
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                  placeholder={t("tasks.objectivePlaceholder")}
                  rows={3}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="startUrl">{t("tasks.startUrlLabel")}</Label>
                <Input
                  id="startUrl"
                  type="url"
                  value={startUrl}
                  onChange={(e) => setStartUrl(e.target.value)}
                  placeholder={t("tasks.startUrlPlaceholder")}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="maxSteps">{t("tasks.maxStepsLabel")}</Label>
                  <Input
                    id="maxSteps"
                    type="number"
                    min={1}
                    max={200}
                    value={maxSteps}
                    onChange={(e) => setMaxSteps(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="maxSeconds">{t("tasks.maxSecondsLabel")}</Label>
                  <Input
                    id="maxSeconds"
                    type="number"
                    min={1}
                    max={3600}
                    value={maxSeconds}
                    onChange={(e) => setMaxSeconds(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="successCriteria">
                  {t("tasks.successCriteriaLabel")}
                </Label>
                <Textarea
                  id="successCriteria"
                  value={successCriteria}
                  onChange={(e) => setSuccessCriteria(e.target.value)}
                  placeholder={t("tasks.successCriteriaPlaceholder")}
                  rows={2}
                />
              </div>

              <div className="flex items-center justify-between rounded-md border px-3 py-2">
                <div>
                  <Label htmlFor="requireConfirmation" className="cursor-pointer">
                    {t("tasks.requireConfirmationLabel")}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t("tasks.requireConfirmationHint")}
                  </p>
                </div>
                <Switch
                  id="requireConfirmation"
                  checked={requireConfirmation}
                  onCheckedChange={setRequireConfirmation}
                />
              </div>

              <div className="flex items-center justify-between rounded-md border px-3 py-2">
                <div>
                  <Label htmlFor="enableDesktopTools" className="cursor-pointer">
                    {t("tasks.enableDesktopToolsLabel")}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t("tasks.enableDesktopToolsHint")}
                  </p>
                </div>
                <Switch
                  id="enableDesktopTools"
                  checked={enableDesktopTools}
                  onCheckedChange={setEnableDesktopTools}
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" disabled={createMut.isPending}>
                <Play className="mr-1.5 h-4 w-4" />
                {createMut.isPending ? t("tasks.starting") : t("tasks.startTask")}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
