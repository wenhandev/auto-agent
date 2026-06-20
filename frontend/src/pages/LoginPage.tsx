import { useEffect, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Workflow } from "lucide-react";
import { ApiError, getOAuthStartUrl } from "@/api-platform";
import { useAuth } from "@/auth/useAuth";
import { routePath, ROUTES } from "@/routes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function LoginPage() {
  const { t } = useTranslation();
  const { login, isAuthenticated, isLoading } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [oauthProviders, setOauthProviders] = useState<string[]>([]);
  const [passwordLoginEnabled, setPasswordLoginEnabled] = useState(true);
  const [providersLoading, setProvidersLoading] = useState(true);

  const from =
    (location.state as { from?: string } | null)?.from ??
    routePath.workflows();

  useEffect(() => {
    void (async () => {
      try {
        const { apiClient } = await import("@/api-platform");
        const data = await apiClient.auth.oauthProviders();
        setOauthProviders(Array.isArray(data.providers) ? data.providers : []);
        setPasswordLoginEnabled(data.password_login_enabled ?? true);
      } catch {
        setOauthProviders([]);
        setPasswordLoginEnabled(true);
      } finally {
        setProvidersLoading(false);
      }
    })();
  }, []);

  if (!isLoading && isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email: email.trim(), password });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 401
          ? t("auth.invalidCredentials")
          : err instanceof Error
            ? err.message
            : String(err);
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  const showGoogle = oauthProviders.includes("google");
  const showPassword = passwordLoginEnabled;
  const showDivider = showGoogle && showPassword;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Workflow className="h-5 w-5" />
          </div>
          <CardTitle>{t("auth.title")}</CardTitle>
          <CardDescription>{t("auth.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {showGoogle ? (
            <Button
              type="button"
              variant="outline"
              disabled={providersLoading || submitting}
              className="w-full"
              onClick={() => {
                window.location.href = getOAuthStartUrl("google");
              }}
            >
              {t("auth.oauthGoogle")}
            </Button>
          ) : null}

          {showDivider ? (
            <div className="relative py-1">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground">
                  {t("auth.oauthDivider")}
                </span>
              </div>
            </div>
          ) : null}

          {showPassword ? (
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">{t("auth.emailLabel")}</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("auth.emailPlaceholder")}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password">{t("auth.passwordLabel")}</Label>
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
                {submitting ? t("auth.signingIn") : t("auth.signIn")}
              </Button>
            </form>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : null}
          <p className="text-center text-sm text-muted-foreground">
            {t("clientDownload.loginPrompt")}{" "}
            <Link
              to={ROUTES.clientDownload}
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              {t("clientDownload.loginLink")}
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
