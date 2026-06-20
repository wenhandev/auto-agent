export type ClientPlatform = "macos" | "windows" | "linux";

export interface ClientDownloadTarget {
  platform: ClientPlatform;
  labelKey: string;
  hintKey: string;
  url: string | null;
}

const DEFAULT_DOWNLOAD_URLS: Record<ClientPlatform, string> = {
  macos: "https://rpa.wenhandev.com/downloads/Auto-Agent-Client-macos.dmg",
  windows: "https://rpa.wenhandev.com/downloads/Auto-Agent-Client-windows.msi",
  linux: "https://rpa.wenhandev.com/downloads/Auto-Agent-Client-linux.AppImage",
};

function envUrl(key: string): string | null {
  const value = import.meta.env[key]?.trim();
  return value || null;
}

/** Resolved download targets for the web UI (env overrides per platform). */
export function clientDownloadTargets(): ClientDownloadTarget[] {
  return [
    {
      platform: "macos",
      labelKey: "clientDownload.platformMac",
      hintKey: "clientDownload.platformMacHint",
      url: envUrl("VITE_CLIENT_DOWNLOAD_MACOS") ?? DEFAULT_DOWNLOAD_URLS.macos,
    },
    {
      platform: "windows",
      labelKey: "clientDownload.platformWindows",
      hintKey: "clientDownload.platformWindowsHint",
      url: envUrl("VITE_CLIENT_DOWNLOAD_WINDOWS") ?? DEFAULT_DOWNLOAD_URLS.windows,
    },
    {
      platform: "linux",
      labelKey: "clientDownload.platformLinux",
      hintKey: "clientDownload.platformLinuxHint",
      url: envUrl("VITE_CLIENT_DOWNLOAD_LINUX") ?? DEFAULT_DOWNLOAD_URLS.linux,
    },
  ];
}

export function clientCloudUrlDefault(): string {
  return (
    import.meta.env.VITE_CLOUD_URL?.trim() ||
    (typeof window !== "undefined" ? window.location.origin : "")
  );
}
