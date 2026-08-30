import { useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DesktopApiError } from "../api";
import { useDesktopAuth } from "../DesktopAuthContext";
import { DesktopSplash } from "../DesktopSplash";

export function DesktopOAuthCallbackPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const { session, loginOAuth } = useDesktopAuth();
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);

  const code = params.get("code");
  const oauthError = params.get("error");

  useEffect(() => {
    if (session || completed || error) return;

    async function finish() {
      if (oauthError) {
        setError(oauthError);
        return;
      }
      if (!code) {
        setError(t("desktop.oauth.noCode"));
        return;
      }
      const cloudUrl = getOAuthCloudUrl();
      if (!cloudUrl) {
        setError(t("desktop.oauth.missingCloudUrl"));
        return;
      }
      try {
        await loginOAuth({ cloudUrl, oauthExchangeCode: code });
        sessionStorage.removeItem("auto-agent.desktop.oauth.cloud_url");
        setCompleted(true);
      } catch (err: unknown) {
        const message =
          err instanceof DesktopApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : String(err);
        setError(message);
      }
    }

    void finish();
  }, [code, oauthError, session, completed, error, loginOAuth, t]);

  if (session || completed) {
    return <Navigate to="/" replace />;
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6">
        <div className="w-full max-w-sm space-y-3 text-center">
          <h1 className="text-lg font-semibold">{t("desktop.oauth.failedTitle")}</h1>
          <p className="text-sm text-muted-foreground">{error}</p>
          <a href="/login" className="text-sm text-primary underline">
            {t("desktop.oauth.backToLogin")}
          </a>
        </div>
      </div>
    );
  }

  return (
    <DesktopSplash
      message={t("desktop.oauth.completing")}
      detail={t("desktop.oauth.registering")}
    />
  );
}

export function setOAuthCloudUrl(cloudUrl: string): void {
  sessionStorage.setItem("auto-agent.desktop.oauth.cloud_url", cloudUrl);
}

export function getOAuthCloudUrl(): string {
  return sessionStorage.getItem("auto-agent.desktop.oauth.cloud_url") || "";
}
