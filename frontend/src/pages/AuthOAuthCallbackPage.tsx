import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api-platform";
import { useAuth } from "@/auth/useAuth";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { routePath } from "@/routes";

export function AuthOAuthCallbackPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { oauthExchange } = useAuth();
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);

  const code = params.get("code") ?? undefined;
  const oauthError = params.get("error") ?? undefined;

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    void (async () => {
      if (oauthError) {
        const message =
          oauthError === "account_not_provisioned"
            ? t("auth.oauthAccountNotProvisioned")
            : oauthError === "oauth_failed"
              ? t("auth.oauthFailed")
              : oauthError;
        setError(message);
        return;
      }
      if (!code) {
        setError(t("auth.oauthFailed"));
        return;
      }
      try {
        await oauthExchange(code);
        navigate(routePath.workflows(), { replace: true });
      } catch (err) {
        const message =
          err instanceof ApiError && err.status === 400
            ? t("auth.oauthFailed")
            : err instanceof Error
              ? err.message
              : String(err);
        setError(message);
      }
    })();
  }, [code, oauthError, oauthExchange, navigate, t]);

  if (!error && !oauthError && code) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>{t("auth.oauthCallbackTitle")}</CardTitle>
            <CardDescription>{t("auth.oauthCallbackWorking")}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (!error) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t("auth.oauthCallbackTitle")}</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={() => navigate("/login", { replace: true })}>
            {t("auth.backToLogin")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
