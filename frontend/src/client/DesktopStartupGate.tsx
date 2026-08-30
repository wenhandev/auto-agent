import { useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { DesktopSplash } from "./DesktopSplash";
import { useRuntimeStatus } from "./RuntimeStatusContext";
import { isTauriShell } from "./tauriShell";

export function DesktopStartupGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { checking } = useRuntimeStatus();

  useEffect(() => {
    if (!isTauriShell()) return;
    void (async () => {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().show();
    })();
  }, []);

  if (checking) {
    return <DesktopSplash message={t("desktop.splash.starting")} />;
  }

  return children;
}
