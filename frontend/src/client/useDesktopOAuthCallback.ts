import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { isTauriShell } from "./tauriShell";

interface OAuthCallbackPayload {
  code?: string | null;
  error?: string | null;
}

function buildCallbackSearch(payload: OAuthCallbackPayload): string {
  const params = new URLSearchParams();
  if (payload.code) params.set("code", payload.code);
  if (payload.error) params.set("error", payload.error);
  return params.toString();
}

type OAuthHandler = (search: string) => void;

let oauthHandler: OAuthHandler | null = null;
let queuedOAuthSearch: string | null = null;

if (isTauriShell()) {
  void (async () => {
    const [{ listen }, { getCurrentWindow }] = await Promise.all([
      import("@tauri-apps/api/event"),
      import("@tauri-apps/api/window"),
    ]);
    await listen<OAuthCallbackPayload>("oauth-callback", (event) => {
      const search = buildCallbackSearch(event.payload);
      if (!search) return;
      void getCurrentWindow().show();
      void getCurrentWindow().setFocus();
      if (oauthHandler) oauthHandler(search);
      else queuedOAuthSearch = search;
    });
  })();
}

/** Listen for OAuth redirects captured by the Tauri localhost callback server. */
export function useDesktopOAuthCallback(): void {
  const navigate = useNavigate();

  useEffect(() => {
    if (!isTauriShell()) return;

    oauthHandler = (search) => {
      navigate(`/login/oauth/callback?${search}`, { replace: true });
    };

    if (queuedOAuthSearch) {
      const search = queuedOAuthSearch;
      queuedOAuthSearch = null;
      oauthHandler(search);
    }

    return () => {
      oauthHandler = null;
    };
  }, [navigate]);
}
