import { useEffect, useState } from "react";
import { fetchSidecarStatus } from "../api";
import type { SidecarStatus } from "../types";
import { Badge } from "@/components/ui/badge";
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

export function OverviewPage() {
  const [status, setStatus] = useState<SidecarStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const next = await fetchSidecarStatus();
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
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="text-sm text-muted-foreground">
          Connection status and environment preflight for this device.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cloud connection</CardTitle>
            <CardDescription>Worker WebSocket to the control plane</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant={status?.connected ? "default" : "secondary"}>
              {status?.connected ? "Connected" : "Disconnected"}
            </Badge>
            {status?.cloud_url && (
              <p className="mt-3 truncate text-sm text-muted-foreground">
                {status.cloud_url}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Environment</CardTitle>
            <CardDescription>Latest preflight summary from the runtime</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant={statusVariant(!!status?.connected, envStatus)}>
              {envStatus}
            </Badge>
            {status?.preflight.checks?.length ? (
              <ul className="mt-3 space-y-1 text-sm text-muted-foreground">
                {status.preflight.checks.slice(0, 5).map((check) => (
                  <li key={check.id}>
                    {check.id}: {check.status} — {check.message}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">
                No preflight data yet. Ensure the runtime sidecar is running.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
