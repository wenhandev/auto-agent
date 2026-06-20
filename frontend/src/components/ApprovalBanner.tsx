import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, X } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import type { ApprovalInputSpec, PendingApproval } from "@/types-platform";
import { captchaKindLabel, isCaptchaApproval } from "@/lib/captchaUtils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

interface Props {
  runId: string;
  pending?: PendingApproval | null;
  onResolved?(): void;
}

function defaultInputValue(spec: ApprovalInputSpec): unknown {
  if (spec.default !== undefined && spec.default !== null) {
    return spec.default;
  }
  return spec.type === "boolean" ? false : "";
}

export function ApprovalBanner({ runId, pending, onResolved }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);

  const pollQuery = useQuery({
    queryKey: ["runs", "approvals", runId],
    queryFn: () => apiClient.approvals.listPending(runId),
    enabled: !!runId && !pending,
    refetchInterval: (query) =>
      (query.state.data?.length ?? 0) > 0 ? false : 2000,
  });

  const active = pending ?? pollQuery.data?.[0] ?? null;

  useEffect(() => {
    if (!active) return;
    const next: Record<string, unknown> = {};
    for (const spec of active.inputs_schema) {
      next[spec.name] = defaultInputValue(spec);
    }
    setInputs(next);
    setError(null);
  }, [active?.node_id, active?.requested_at]);

  const resolveMut = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      apiClient.approvals.resolve(runId, active!.node_id, {
        decision,
        inputs: decision === "approve" ? inputs : {},
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["runs", "approvals", runId],
      });
      onResolved?.();
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        const body = err.body as { detail?: unknown };
        setError(
          typeof body?.detail === "string"
            ? body.detail
            : t("approval.resolveError"),
        );
      } else {
        setError(err instanceof Error ? err.message : t("approval.resolveError"));
      }
    },
  });

  if (!active) return null;

  const captchaApproval = isCaptchaApproval(active);
  const captchaKind = active.captcha_kind ?? null;

  return (
    <div
      id="approval-banner"
      className="border-b border-amber-500/40 bg-amber-500/10 px-4 py-3"
    >
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
            {captchaApproval
              ? t("approval.captchaBannerTitle")
              : t("approval.bannerTitle")}
          </p>
          {captchaApproval && captchaKind && (
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-[10px]">
                {captchaKindLabel(captchaKind, (key, fallback) =>
                  t(key, fallback ?? key),
                )}
              </Badge>
            </div>
          )}
          {captchaApproval && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("approval.captchaInstruction")}
            </p>
          )}
          <p className="mt-1 text-sm font-medium">{active.prompt}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {active.node_id}
          </p>
        </div>

        {active.inputs_schema.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {active.inputs_schema.map((spec) => {
              const label = spec.label || spec.name;
              const value = inputs[spec.name];

              if (spec.type === "boolean") {
                return (
                  <div
                    key={spec.name}
                    className="flex items-center justify-between gap-2 rounded-md border bg-background/60 px-3 py-2"
                  >
                    <Label htmlFor={`approval-${spec.name}`}>{label}</Label>
                    <Switch
                      id={`approval-${spec.name}`}
                      checked={Boolean(value)}
                      onCheckedChange={(checked) =>
                        setInputs((prev) => ({
                          ...prev,
                          [spec.name]: checked,
                        }))
                      }
                      disabled={resolveMut.isPending}
                    />
                  </div>
                );
              }

              return (
                <div key={spec.name} className="flex flex-col gap-1">
                  <Label htmlFor={`approval-${spec.name}`}>
                    {label}
                    {spec.required && " *"}
                  </Label>
                  <Input
                    id={`approval-${spec.name}`}
                    type={spec.type === "number" ? "number" : "text"}
                    value={
                      value === undefined || value === null ? "" : String(value)
                    }
                    onChange={(e) =>
                      setInputs((prev) => ({
                        ...prev,
                        [spec.name]:
                          spec.type === "number"
                            ? e.target.value === ""
                              ? ""
                              : Number(e.target.value)
                            : e.target.value,
                      }))
                    }
                    disabled={resolveMut.isPending}
                  />
                </div>
              );
            })}
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => resolveMut.mutate("approve")}
            disabled={resolveMut.isPending}
          >
            <Check className="mr-1.5 h-3.5 w-3.5" />
            {t("approval.approve")}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => resolveMut.mutate("reject")}
            disabled={resolveMut.isPending}
          >
            <X className="mr-1.5 h-3.5 w-3.5" />
            {t("approval.reject")}
          </Button>
        </div>
      </div>
    </div>
  );
}
