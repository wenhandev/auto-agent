import { setApiBaseUrl, setApiBearerToken } from "@/api-platform";
import type { DesktopSession } from "./types";

function proxyTarget(): string {
  return (import.meta.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001").replace(
    /\/$/,
    "",
  );
}

/** Wire shared web API client to the logged-in desktop cloud session. */
export function configureCloudApi(session: DesktopSession | null): void {
  if (!session) {
    setApiBearerToken(null);
    setApiBaseUrl(null);
    return;
  }
  setApiBearerToken(session.webSessionToken);
  const cloudUrl = session.cloudUrl.replace(/\/$/, "");
  if (import.meta.env.DEV && cloudUrl === proxyTarget()) {
    setApiBaseUrl(null);
  } else {
    setApiBaseUrl(cloudUrl);
  }
}
