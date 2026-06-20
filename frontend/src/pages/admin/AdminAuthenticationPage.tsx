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

function StatusBadge({ enabled }: { enabled: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={
        enabled
          ? "inline-flex rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400"
          : "inline-flex rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
      }
    >
      {enabled ? t("admin.authentication.enabled") : t("admin.authentication.disabled")}
    </span>
  );
}

export function AdminAuthenticationPage() {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["admin", "auth-settings"],
    queryFn: () => apiClient.admin.authSettings(),
  });

  const settings = query.data;
  const signupPolicyLabel =
    settings?.signup_policy === "domain_allowlist"
      ? t("admin.authentication.signupDomainAllowlist")
      : t("admin.authentication.signupExistingOnly");

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle>{t("admin.authentication.title")}</CardTitle>
        <CardDescription>{t("admin.authentication.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {query.isLoading || !settings ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">
                  {t("admin.authentication.google")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <StatusBadge enabled={settings.providers.google} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">
                  {t("admin.authentication.passwordLogin")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <StatusBadge enabled={settings.password_login_enabled} />
              </CardContent>
            </Card>
            <Card className="sm:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">
                  {t("admin.authentication.signupPolicy")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">{signupPolicyLabel}</p>
              </CardContent>
            </Card>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
