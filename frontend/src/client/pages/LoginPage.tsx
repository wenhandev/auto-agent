import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  DesktopApiError,
  fetchOAuthProviders,
  getDesktopOAuthStartUrl,
} from "../api";
import { useDesktopAuth } from "../DesktopAuthContext";
import { desktopDefaultCloudUrl, isDesktopCloudUrlBakedIn } from "../cloudUrl";
import { openExternalUrl } from "../tauriShell";
import { setOAuthCloudUrl } from "./OAuthCallbackPage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Workflow } from "lucide-react";

const cloudUrlBakedIn = isDesktopCloudUrlBakedIn();
const appVersion = import.meta.env.VITE_APP_VERSION?.trim();

export function DesktopLoginPage() {
  const { t } = useTranslation();
  const { session, isLoading, login } = useDesktopAuth();
  const [cloudUrl, setCloudUrl] = useState(desktopDefaultCloudUrl());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [oauthPending, setOauthPending] = useState(false);
  const [oauthProviders, setOauthProviders] = useState<string[]>(
    cloudUrlBakedIn ? ["google"] : [],
  );
  const [passwordLoginEnabled, setPasswordLoginEnabled] = useState(
    !cloudUrlBakedIn,
  );
  const [providersLoading, setProvidersLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setProvidersLoading(true);
    void fetchOAuthProviders(cloudUrl)
      .then((data) => {
        if (cancelled) return;
        setOauthProviders(Array.isArray(data.providers) ? data.providers : []);
        setPasswordLoginEnabled(data.password_login_enabled !== false);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!cloudUrlBakedIn) {
          const message =
            err instanceof DesktopApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : String(err);
          setError(message);
        }
      })
      .finally(() => {
        if (!cancelled) setProvidersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cloudUrl]);

  if (!isLoading && session) {
    if (session.approvalStatus === "pending") {
      return <Navigate to="/pending" replace />;
    }
    if (session.approvalStatus === "rejected") {
      return <Navigate to="/login" replace />;
    }
    return <Navigate to="/" replace />;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ cloudUrl, email, password });
    } catch (err: unknown) {
      const message =
        err instanceof DesktopApiError && err.status === 401
          ? t("desktop.login.invalidCredentials")
          : err instanceof DesktopApiError && err.status === 403
            ? t("desktop.login.clientsDisabled")
            : err instanceof Error
              ? err.message
              : String(err);
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  async function onGoogleSignIn() {
    setError(null);
    setOauthPending(true);
    try {
      setOAuthCloudUrl(cloudUrl.trim().replace(/\/$/, ""));
      await openExternalUrl(getDesktopOAuthStartUrl(cloudUrl, "google"));
    } catch (err: unknown) {
      setOauthPending(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const showGoogle =
    oauthProviders.includes("google") ||
    (cloudUrlBakedIn && providersLoading);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 py-8">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-2 text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Workflow className="h-5 w-5" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">{t("nav.brand")}</h1>
          <p className="text-sm text-muted-foreground">
            {cloudUrlBakedIn
              ? t("desktop.login.subtitleBakedIn")
              : t("desktop.login.subtitleDefault")}
          </p>
        </div>

        {oauthPending ? (
          <div className="space-y-4 rounded-lg border bg-muted/20 p-4 text-center">
            <p className="text-sm font-medium">
              {t("desktop.login.oauthPendingTitle")}
            </p>
            <p className="text-xs text-muted-foreground">
              {t("desktop.login.oauthPendingHint")}
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                type="button"
                variant="outline"
                className="flex-1"
                onClick={() => setOauthPending(false)}
              >
                {t("desktop.login.cancel")}
              </Button>
              <Button
                type="button"
                className="flex-1"
                onClick={() => void onGoogleSignIn()}
              >
                {t("desktop.login.openBrowserAgain")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {!cloudUrlBakedIn && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cloud-url">{t("desktop.login.cloudUrl")}</Label>
                <Input
                  id="cloud-url"
                  type="url"
                  value={cloudUrl}
                  onChange={(e) => setCloudUrl(e.target.value)}
                  placeholder={t("desktop.login.cloudUrlPlaceholder")}
                  required
                />
              </div>
            )}

            {showGoogle && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  disabled={providersLoading}
                  onClick={() => void onGoogleSignIn()}
                >
                  {providersLoading
                    ? t("desktop.login.loadingSignIn")
                    : t("desktop.login.continueGoogle")}
                </Button>
                {passwordLoginEnabled && (
                  <p className="text-center text-xs text-muted-foreground">
                    {t("desktop.login.or")}
                  </p>
                )}
              </>
            )}

            {passwordLoginEnabled && (
              <form onSubmit={onSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="email">{t("desktop.login.email")}</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="password">{t("desktop.login.password")}</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button type="submit" disabled={submitting} className="w-full">
                  {submitting
                    ? t("desktop.login.signingIn")
                    : t("desktop.login.signInPassword")}
                </Button>
              </form>
            )}

            {!passwordLoginEnabled && error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
          </div>
        )}

        {appVersion ? (
          <p className="text-center text-xs text-muted-foreground/70">
            {t("desktop.login.version", { version: appVersion })}
          </p>
        ) : null}
      </div>
    </div>
  );
}
