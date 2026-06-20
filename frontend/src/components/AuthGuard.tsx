import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/useAuth";
import { ROUTES } from "@/routes";

export function AuthGuard() {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading, bypass } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center text-sm text-muted-foreground">
        {t("common.loading")}
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <Navigate
        to={ROUTES.login}
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  return (
    <>
      {bypass && (
        <div className="border-b border-amber-500/40 bg-amber-500/10 px-4 py-1 text-center text-xs text-amber-700 dark:text-amber-300">
          {t("auth.bypassBanner")}
        </div>
      )}
      <Outlet />
    </>
  );
}
