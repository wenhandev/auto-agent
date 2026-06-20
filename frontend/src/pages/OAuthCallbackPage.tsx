import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { IntegrationAppLabel } from "@/components/IntegrationAppLabel";
import { routePath } from "@/routes";

export function OAuthCallbackPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const connected = params.get("connected") === "1";
  const app = params.get("app") ?? "";
  const error = params.get("error") ?? "";

  useEffect(() => {
    if (connected && app) {
      toast.success(t("pages.credentials.oauthSuccess", { app }));
    } else if (error) {
      toast.error(t("pages.credentials.oauthError", { error }));
    }
    const timer = window.setTimeout(() => {
      navigate(routePath.credentials(), { replace: true });
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [connected, app, error, navigate, t]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      {connected && app ? (
        <>
          <div className="text-lg font-medium">
            {t("pages.credentials.oauthCallbackTitle")}
          </div>
          <IntegrationAppLabel app={app} className="text-base" />
          <p className="text-sm text-muted-foreground">
            {t("pages.credentials.oauthCallbackRedirect")}
          </p>
        </>
      ) : (
        <>
          <div className="text-lg font-medium text-destructive">
            {t("pages.credentials.oauthCallbackFailed")}
          </div>
          {error && (
            <p className="text-sm text-muted-foreground">{error}</p>
          )}
        </>
      )}
    </div>
  );
}
