import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { scheduleRuntimeSync, syncRuntimeSession } from "./api";
import { useDesktopAuth } from "./DesktopAuthContext";
import { useRuntimeConnectionStatus } from "./useRuntimeConnectionStatus";
import { useRuntimeStatus } from "./RuntimeStatusContext";
import { Button } from "@/components/ui/button";

const bannerClassName =
  "border-b border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-950 dark:text-amber-100";

export function WorkerCloudWarningBanner() {
  const { t } = useTranslation();
  const { session } = useDesktopAuth();
  const { ready: runtimeStartupReady } = useRuntimeStatus();
  const { connected, status, refresh } = useRuntimeConnectionStatus();
  const [retrying, setRetrying] = useState(false);

  if (!session || !runtimeStartupReady || !status || connected) {
    return null;
  }

  async function handleRetry() {
    if (!session) return;
    setRetrying(true);
    try {
      await syncRuntimeSession(session);
    } catch {
      scheduleRuntimeSync(session);
    } finally {
      await refresh();
      setRetrying(false);
    }
  }

  return (
    <div
      role="alert"
      className={bannerClassName}
      style={{ backgroundColor: "rgba(245, 158, 11, 0.12)" }}
    >
      <div className="flex flex-wrap items-start gap-3 sm:items-center">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 sm:mt-0" aria-hidden />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-medium">{t("desktop.workerCloud.bannerTitle")}</p>
          <p className="text-xs leading-relaxed opacity-90">
            {t("desktop.workerCloud.bannerDescription")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={retrying}
            onClick={() => void handleRetry()}
          >
            {retrying ? t("desktop.workerCloud.retrying") : t("desktop.workerCloud.retry")}
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to="/device">{t("desktop.workerCloud.viewDeviceStatus")}</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
