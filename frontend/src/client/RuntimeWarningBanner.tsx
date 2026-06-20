import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRuntimeStatus } from "./RuntimeStatusContext";

export function RuntimeWarningBanner() {
  const { ready, checking, cloudReady, sidecarReady, retry } =
    useRuntimeStatus();

  if (ready || checking) return null;

  const parts: string[] = [];
  if (!cloudReady) parts.push("local cloud");
  if (!sidecarReady) parts.push("runtime sidecar");

  return (
    <div
      role="status"
      className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-950 dark:text-amber-100"
      style={{ backgroundColor: "rgba(245, 158, 11, 0.12)" }}
    >
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-2 text-center">
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
        <span>
          Starting local services… ({parts.join(" and ")} not ready yet). Some
          features may fail until both are running.
        </span>
        <Button type="button" variant="outline" size="sm" onClick={retry}>
          Retry
        </Button>
      </div>
    </div>
  );
}
