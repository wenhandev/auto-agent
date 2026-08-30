import { useCallback, useEffect, useState } from "react";
import { fetchRuntimeStatus } from "./api";
import type { SidecarStatus } from "./types";

const DEFAULT_POLL_MS = 8000;

export function useRuntimeConnectionStatus(pollMs = DEFAULT_POLL_MS) {
  const [status, setStatus] = useState<SidecarStatus | null>(null);

  const refresh = useCallback(async () => {
    const next = await fetchRuntimeStatus();
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const next = await fetchRuntimeStatus();
      if (!cancelled) setStatus(next);
    }
    void poll();
    const id = window.setInterval(() => void poll(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollMs]);

  return {
    status,
    connected: status?.connected ?? false,
    loggedIn: status?.logged_in ?? false,
    refresh,
  };
}
