import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { isDesktopCloudUrlBakedIn } from "./cloudUrl";
import { useRuntimeStatus } from "./RuntimeStatusContext";

export function RuntimeWarningBanner() {
  const { t } = useTranslation();
  const { ready, checking, cloudReady, runtimeReady, retry } =
    useRuntimeStatus();
  const production = isDesktopCloudUrlBakedIn();

  if (ready || checking) return null;

  if (production) {
    if (runtimeReady) return null;
    return (
      <div
        role="status"
        className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-950 dark:text-amber-100"
        style={{ backgroundColor: "rgba(245, 158, 11, 0.12)" }}
      >
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-2 text-center">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
          <span>{t("desktop.runtime.startingProduction")}</span>
          <Button type="button" variant="outline" size="sm" onClick={retry}>
            {t("desktop.runtime.retry")}
          </Button>
        </div>
      </div>
    );
  }

  const parts: string[] = [];
  if (!cloudReady) parts.push(t("desktop.runtime.localCloud"));
  if (!runtimeReady) parts.push(t("desktop.runtime.localRuntime"));

  return (
    <div
      role="status"
      className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-950 dark:text-amber-100"
      style={{ backgroundColor: "rgba(245, 158, 11, 0.12)" }}
    >
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-2 text-center">
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
        <span>
          {t("desktop.runtime.startingDev", {
            parts: parts.join(t("desktop.runtime.and")),
          })}
        </span>
        <Button type="button" variant="outline" size="sm" onClick={retry}>
          {t("desktop.runtime.retry")}
        </Button>
      </div>
    </div>
  );
}
