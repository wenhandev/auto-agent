export type ClientPlatform = "macos" | "windows" | "linux";

export interface ClientDownloadTarget {
  platform: ClientPlatform;
  labelKey: string;
  hintKey: string;
  url: string | null;
}

const DEFAULT_RELEASES_URL =
  "https://github.com/wenhandev/auto-agent/releases";

function envUrl(key: string): string | null {
  const value = import.meta.env[key]?.trim();
  return value || null;
}

/** Resolved download targets for the web UI (env overrides per platform). */
export function clientDownloadTargets(): ClientDownloadTarget[] {
  const releases = envUrl("VITE_CLIENT_RELEASES_URL") ?? DEFAULT_RELEASES_URL;

  return [
    {
      platform: "macos",
      labelKey: "clientDownload.platformMac",
      hintKey: "clientDownload.platformMacHint",
      url: envUrl("VITE_CLIENT_DOWNLOAD_MACOS") ?? releases,
    },
    {
      platform: "windows",
      labelKey: "clientDownload.platformWindows",
      hintKey: "clientDownload.platformWindowsHint",
      url: envUrl("VITE_CLIENT_DOWNLOAD_WINDOWS") ?? releases,
    },
    {
      platform: "linux",
      labelKey: "clientDownload.platformLinux",
      hintKey: "clientDownload.platformLinuxHint",
      url: envUrl("VITE_CLIENT_DOWNLOAD_LINUX") ?? releases,
    },
  ];
}

export function clientCloudUrlDefault(): string {
  return (
    import.meta.env.VITE_CLOUD_URL?.trim() ||
    (typeof window !== "undefined" ? window.location.origin : "")
  );
}
