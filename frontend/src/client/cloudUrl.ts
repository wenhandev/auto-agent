const LOCAL_DEV_CLOUD_URL = "http://127.0.0.1:8001";

export function desktopDefaultCloudUrl(): string {
  return import.meta.env.VITE_CLOUD_URL?.trim() || LOCAL_DEV_CLOUD_URL;
}

export function isLocalDevCloudUrl(url: string): boolean {
  try {
    const { hostname } = new URL(url);
    return hostname === "127.0.0.1" || hostname === "localhost";
  } catch {
    return false;
  }
}

/** True when build baked in a non-local cloud URL (production installers). */
export function isDesktopCloudUrlBakedIn(): boolean {
  const baked = import.meta.env.VITE_CLOUD_URL?.trim();
  if (!baked) return false;
  return !isLocalDevCloudUrl(baked);
}
