import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiClient, ApiError } from "@/api-platform";
import type { LlmConfigTestResult } from "@/api-platform";
import type { LlmConfigOut, LlmConfigUpsert } from "@/types-platform";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";

const QK_LIST = ["llmConfig", "list"] as const;
const QK_EFFECTIVE = ["llmConfig", "effective"] as const;

type Provider = "openai" | "google";

function deriveActive(rows: LlmConfigOut[] | undefined): LlmConfigOut | null {
  if (!rows) return null;
  return rows.find((r) => r.is_active) ?? rows[0] ?? null;
}

export function SettingsLlmTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const effectiveQuery = useQuery({
    queryKey: QK_EFFECTIVE,
    queryFn: () => apiClient.llmConfig.effective(),
  });

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: () => apiClient.llmConfig.list(),
  });

  const active = deriveActive(listQuery.data);

  const [provider, setProvider] = useState<Provider>("openai");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [selfHealEnabled, setSelfHealEnabled] = useState(true);
  const [selfHealThreshold, setSelfHealThreshold] = useState(0.6);
  const [hydrated, setHydrated] = useState(false);
  const [testResult, setTestResult] = useState<LlmConfigTestResult | null>(null);

  useEffect(() => {
    if (active && !hydrated) {
      setProvider((active.provider as Provider) ?? "openai");
      setModel(active.model);
      setBaseUrl(active.base_url ?? "");
      setSelfHealEnabled(
        active.self_healing_enabled === undefined ? true : active.self_healing_enabled,
      );
      const threshold = active.self_healing_vision_threshold;
      setSelfHealThreshold(typeof threshold === "number" ? threshold : 0.6);
      setHydrated(true);
    }
  }, [active, hydrated]);

  const upsertMut = useMutation({
    mutationFn: (body: LlmConfigUpsert) => apiClient.llmConfig.upsert(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
      void queryClient.invalidateQueries({ queryKey: QK_EFFECTIVE });
      void queryClient.invalidateQueries({ queryKey: ["llmConfig"] });
    },
  });

  const testMut = useMutation({
    mutationFn: (body: LlmConfigUpsert) => apiClient.llmConfig.test(body),
    onSuccess: (r) => setTestResult(r),
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
          : err instanceof Error
            ? err.message
            : String(err);
      setTestResult({ ok: false, error: message });
    },
  });

  function buildPayload(): LlmConfigUpsert {
    return {
      provider,
      model: model.trim(),
      api_key: apiKey,
      base_url: baseUrl.trim() || null,
      self_healing_enabled: selfHealEnabled,
      self_healing_vision_threshold: selfHealThreshold,
    };
  }

  const upsertError = upsertMut.error as unknown;
  const upsertErrorMsg =
    upsertError instanceof ApiError
      ? `${upsertError.status}: ${typeof upsertError.body === "string" ? upsertError.body : JSON.stringify(upsertError.body)}`
      : upsertError instanceof Error
        ? upsertError.message
        : null;

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle className="text-base">
          {t("pages.settings.llmConfigTitle")}
        </CardTitle>
        <CardDescription>
          {t("pages.settings.llmConfigDescription")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {effectiveQuery.data && effectiveQuery.data.source !== "none" && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border bg-muted/40 px-4 py-3 text-xs">
            <Badge variant="secondary">
              {t("pages.settings.effectiveBannerLabel")}
            </Badge>
            <span>
              {t("pages.settings.effectiveSource")}:{" "}
              <code className="font-mono">{effectiveQuery.data.source}</code>
            </span>
            <span>
              {t("pages.settings.effectiveProvider")}:{" "}
              <code className="font-mono">{effectiveQuery.data.provider}</code>
            </span>
            <span>
              {t("pages.settings.effectiveModel")}:{" "}
              <code className="font-mono">{effectiveQuery.data.model}</code>
            </span>
            <span>
              {t("pages.settings.effectiveKey")}:{" "}
              <code className="font-mono">{effectiveQuery.data.api_key_masked}</code>
            </span>
          </div>
        )}
        {effectiveQuery.data?.source === "none" && (
          <div className="rounded-md border border-dashed bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
            {t(
              "pages.settings.effectiveNone",
              "No LLM configuration is active yet. Save a provider and model below.",
            )}
          </div>
        )}
        {effectiveQuery.error && (
          <div className="text-sm text-destructive">
            {t("pages.settings.effectiveError", {
              error: (effectiveQuery.error as Error).message,
            })}
          </div>
        )}

        <div className="grid max-w-2xl gap-4">
          <div className="grid gap-2">
            <Label>{t("pages.settings.providerLabel")}</Label>
            <div className="flex items-center gap-3">
              {(["openai", "google"] as const).map((opt) => (
                <label
                  key={opt}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm",
                    provider === opt
                      ? "border-primary bg-primary/10 text-foreground"
                      : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  <input
                    type="radio"
                    name="provider"
                    className="sr-only"
                    checked={provider === opt}
                    onChange={() => setProvider(opt)}
                  />
                  {opt}
                </label>
              ))}
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="settings-model">{t("pages.settings.modelLabel")}</Label>
            <Input
              id="settings-model"
              name="llm-model"
              autoComplete="off"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={provider === "openai" ? "gpt-4o-mini" : "gemini-2.0-flash"}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="settings-key">{t("pages.settings.apiKeyLabel")}</Label>
            <Input
              id="settings-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                active
                  ? t("pages.settings.apiKeyKeep", { masked: active.api_key_masked })
                  : t("pages.settings.apiKeyPlaceholder")
              }
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="settings-base">{t("pages.settings.baseUrlLabel")}</Label>
            <Input
              id="settings-base"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={t("pages.settings.baseUrlPlaceholder")}
            />
          </div>

          <div className="grid gap-3 rounded-md border bg-muted/30 px-4 py-3">
            <div className="flex items-center justify-between gap-4">
              <div className="grid gap-0.5">
                <Label htmlFor="settings-selfheal">
                  {t("pages.settings.selfHealLabel")}
                </Label>
                <span className="text-xs text-muted-foreground">
                  {t("pages.settings.selfHealDescription")}
                </span>
              </div>
              <Switch
                id="settings-selfheal"
                checked={selfHealEnabled}
                onCheckedChange={setSelfHealEnabled}
              />
            </div>
            {selfHealEnabled && (
              <div className="grid gap-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="settings-selfheal-threshold">
                    {t("pages.settings.selfHealThresholdLabel")}
                  </Label>
                  <span className="font-mono text-xs text-muted-foreground">
                    {selfHealThreshold.toFixed(2)}
                  </span>
                </div>
                <Slider
                  id="settings-selfheal-threshold"
                  min={0}
                  max={1}
                  step={0.05}
                  value={[selfHealThreshold]}
                  onValueChange={(v) => setSelfHealThreshold(v[0] ?? 0.6)}
                />
              </div>
            )}
          </div>

          {testResult && (
            <div
              className={cn(
                "rounded-md border px-3 py-2 text-sm",
                testResult.ok
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                  : "border-destructive/40 bg-destructive/10 text-destructive",
              )}
            >
              {testResult.ok
                ? (testResult.message ?? t("pages.settings.testPassed"))
                : (testResult.error ?? t("pages.settings.testFailed"))}
            </div>
          )}
          {upsertErrorMsg && (
            <div className="text-sm text-destructive">{upsertErrorMsg}</div>
          )}

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => {
                setTestResult(null);
                if (!model.trim()) {
                  setTestResult({ ok: false, error: t("pages.settings.modelRequired") });
                  return;
                }
                testMut.mutate(buildPayload());
              }}
              disabled={testMut.isPending}
            >
              {testMut.isPending
                ? t("pages.settings.testing")
                : t("pages.settings.testButton")}
            </Button>
            <Button
              onClick={() => {
                if (!model.trim()) return;
                upsertMut.mutate(buildPayload());
              }}
              disabled={upsertMut.isPending}
            >
              {upsertMut.isPending
                ? t("pages.settings.saving")
                : t("pages.settings.saveButton")}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
