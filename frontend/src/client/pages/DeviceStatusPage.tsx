import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { fetchRuntimeStatus } from "../api";
import { friendlyCheckLabel, friendlyEnvStatus } from "../deviceStatus";
import type { SidecarStatus } from "../types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function statusVariant(
  connected: boolean,
  envStatus: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (!connected) return "secondary";
  if (envStatus === "ready") return "default";
  if (envStatus === "not_ready") return "destructive";
  return "outline";
}

function checkVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "pass") return "default";
  if (status === "warn") return "outline";
  return "destructive";
}

/** Technical device / preflight detail (linked from Home and Settings). */
export function DeviceStatusPage() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<SidecarStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const next = await fetchRuntimeStatus();
      if (!cancelled) setStatus(next);
    }
    void poll();
    const id = window.setInterval(() => void poll(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const envStatus = status?.preflight.environment_status ?? "unknown";

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("desktop.device.title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("desktop.device.subtitle")}
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to="/">{t("desktop.device.backHome")}</Link>
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {t("desktop.device.cloudLinkTitle")}
            </CardTitle>
            <CardDescription>
              {t("desktop.device.cloudLinkDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant={status?.connected ? "default" : "secondary"}>
              {status?.connected
                ? t("desktop.device.online")
                : t("desktop.device.offline")}
            </Badge>
            <p className="mt-3 text-sm text-muted-foreground">
              {status?.connected
                ? t("desktop.device.cloudConnectedHint")
                : t("desktop.device.cloudDisconnectedHint")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {t("desktop.device.localSetupTitle")}
            </CardTitle>
            <CardDescription>
              {t("desktop.device.localSetupDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant={statusVariant(!!status?.connected, envStatus)}>
              {friendlyEnvStatus(envStatus)}
            </Badge>
            {status?.preflight.checks?.length ? (
              <ul className="mt-3 space-y-2 text-sm">
                {status.preflight.checks.map((check) => (
                  <li
                    key={check.id}
                    className="flex flex-wrap items-center gap-2 text-muted-foreground"
                  >
                    <Badge variant={checkVariant(check.status)} className="text-xs">
                      {check.status}
                    </Badge>
                    <span className="font-medium text-foreground">
                      {friendlyCheckLabel(check.id)}
                    </span>
                    {check.status !== "pass" ? (
                      <span className="text-xs">{check.message}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">
                {t("desktop.device.checking")}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** @deprecated use DeviceStatusPage — kept for route alias */
export const OverviewPage = DeviceStatusPage;
