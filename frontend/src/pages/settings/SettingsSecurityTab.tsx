import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiClient } from "@/api-platform";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";

const QK_ANTIBOT = ["settings", "antibot"] as const;

export function SettingsSecurityTab() {
  const { t } = useTranslation();

  const antibotQuery = useQuery({
    queryKey: QK_ANTIBOT,
    queryFn: () => apiClient.settings.antibot(),
  });

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle className="text-base">{t("pages.settings.antibotTitle")}</CardTitle>
        <CardDescription>{t("pages.settings.antibotDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {antibotQuery.isLoading && (
          <p className="text-sm text-muted-foreground">
            {t("pages.settings.antibotLoading")}
          </p>
        )}
        {antibotQuery.error && (
          <p className="text-sm text-destructive">
            {t("pages.settings.antibotError", {
              error: (antibotQuery.error as Error).message,
            })}
          </p>
        )}
        {antibotQuery.data && (
          <>
            <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-4 py-3 text-xs">
              <Badge variant="secondary">
                {t("pages.settings.antibotReadOnlyBadge")}
              </Badge>
              <span className="text-muted-foreground">
                {t("pages.settings.antibotEnvHint")}
              </span>
            </div>
            <div className="grid max-w-2xl gap-4">
              <div className="flex items-center justify-between gap-4 rounded-md border bg-muted/30 px-4 py-3">
                <div className="grid gap-0.5">
                  <Label>{t("pages.settings.captchaDetectionLabel")}</Label>
                  <span className="text-xs text-muted-foreground">
                    {t("pages.settings.captchaDetectionDescription")}
                  </span>
                </div>
                <Switch checked={antibotQuery.data.captcha_detection_enabled} disabled />
              </div>
              <div className="flex items-center justify-between gap-4 rounded-md border bg-muted/30 px-4 py-3">
                <div className="grid gap-0.5">
                  <Label>{t("pages.settings.captchaHeuristicsLabel")}</Label>
                  <span className="text-xs text-muted-foreground">
                    {t("pages.settings.captchaHeuristicsDescription")}
                  </span>
                </div>
                <Switch
                  checked={antibotQuery.data.captcha_builtin_heuristics_enabled}
                  disabled
                />
              </div>
              <div className="grid gap-2">
                <Label>{t("pages.settings.captchaSolverLabel")}</Label>
                <Input
                  value={t(
                    `pages.settings.captchaSolver.${antibotQuery.data.captcha_solver}`,
                    antibotQuery.data.captcha_solver,
                  )}
                  readOnly
                  disabled
                />
              </div>
              {antibotQuery.data.captcha_solver === "external" && (
                <div className="grid gap-2">
                  <Label>{t("pages.settings.captchaExternalUrlLabel")}</Label>
                  <Input
                    value={
                      antibotQuery.data.captcha_external_solver_url_masked ??
                      t("pages.settings.notConfigured")
                    }
                    readOnly
                    disabled
                  />
                  <p className="text-xs text-muted-foreground">
                    {t("pages.settings.captchaExternalKeyLabel")}:{" "}
                    {antibotQuery.data.captcha_external_solver_key_configured
                      ? t("pages.settings.configured")
                      : t("pages.settings.notConfigured")}
                  </p>
                </div>
              )}
              <div className="flex items-center justify-between gap-4 rounded-md border bg-muted/30 px-4 py-3">
                <div className="grid gap-0.5">
                  <Label>{t("pages.settings.antibotStealthLabel")}</Label>
                  <span className="text-xs text-muted-foreground">
                    {t("pages.settings.antibotStealthDescription")}
                  </span>
                </div>
                <Switch checked={antibotQuery.data.antibot_stealth} disabled />
              </div>
              <div className="grid gap-2 rounded-md border bg-muted/20 px-4 py-3 text-sm">
                <p className="font-medium">{t("pages.settings.proxySectionTitle")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("pages.settings.proxySectionDescription")}
                </p>
                <dl className="mt-2 grid gap-1 text-xs">
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground">
                      {t("pages.settings.proxyConfiguredLabel")}
                    </dt>
                    <dd>
                      {antibotQuery.data.proxy_configured
                        ? t("pages.settings.yes")
                        : t("pages.settings.no")}
                    </dd>
                  </div>
                  {antibotQuery.data.proxy_url_masked && (
                    <div className="flex gap-2">
                      <dt className="text-muted-foreground">
                        {t("pages.settings.proxyUrlLabel")}
                      </dt>
                      <dd>
                        <code className="font-mono">
                          {antibotQuery.data.proxy_url_masked}
                        </code>
                      </dd>
                    </div>
                  )}
                  {antibotQuery.data.default_proxy_id && (
                    <div className="flex gap-2">
                      <dt className="text-muted-foreground">
                        {t("pages.settings.defaultProxyIdLabel")}
                      </dt>
                      <dd>
                        <code className="font-mono">
                          {antibotQuery.data.default_proxy_id}
                        </code>
                      </dd>
                    </div>
                  )}
                </dl>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  {t("pages.settings.proxyEnvVarsHint")}
                </p>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
