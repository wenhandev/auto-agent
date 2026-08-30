import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Clock, ShieldAlert } from "lucide-react";
import { useDesktopAuth } from "../DesktopAuthContext";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function PendingAuthorizationPage() {
  const { t } = useTranslation();
  const { session, isLoading, refreshApproval, logout } = useDesktopAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session || session.approvalStatus !== "pending") return;
    const id = window.setInterval(() => {
      void refreshApproval().catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      });
    }, 10_000);
    return () => window.clearInterval(id);
  }, [session, refreshApproval]);

  if (!isLoading && !session) {
    return <Navigate to="/login" replace />;
  }
  if (!isLoading && session?.approvalStatus === "approved") {
    return <Navigate to="/" replace />;
  }
  if (!isLoading && session?.approvalStatus === "rejected") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <ShieldAlert className="mx-auto mb-2 h-10 w-10 text-destructive" />
            <CardTitle>{t("desktop.pending.rejectedTitle")}</CardTitle>
            <CardDescription>
              {t("desktop.pending.rejectedDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" className="w-full" onClick={() => logout()}>
              {t("desktop.signOut")}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <Clock className="mx-auto mb-2 h-10 w-10 text-muted-foreground" />
          <CardTitle>{t("desktop.pending.waitingTitle")}</CardTitle>
          <CardDescription>{t("desktop.pending.waitingDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-center text-sm text-muted-foreground">
            {t("desktop.pending.checkingInterval")}
          </p>
          {error && <p className="text-center text-sm text-destructive">{error}</p>}
          <div className="flex gap-2">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() => void refreshApproval()}
            >
              {t("desktop.pending.checkNow")}
            </Button>
            <Button variant="outline" className="flex-1" onClick={() => logout()}>
              {t("desktop.signOut")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
