import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  fetchCloudHealth,
  fetchSidecarHealth,
  waitForRuntime,
} from "./api";

interface RuntimeStatus {
  cloudReady: boolean;
  sidecarReady: boolean;
  ready: boolean;
  checking: boolean;
  retry: () => void;
}

const RuntimeStatusContext = createContext<RuntimeStatus | null>(null);

const POLL_MS = 500;
const SOFT_TIMEOUT_MS = 8_000;

export function RuntimeStatusProvider({ children }: { children: ReactNode }) {
  const [cloudReady, setCloudReady] = useState(false);
  const [sidecarReady, setSidecarReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setChecking(true);
    setCloudReady(false);
    setSidecarReady(false);

    async function pollOnce() {
      const [cloud, sidecar] = await Promise.all([
        fetchCloudHealth(),
        fetchSidecarHealth(),
      ]);
      if (cancelled) return;
      setCloudReady(cloud);
      setSidecarReady(sidecar);
      if (cloud && sidecar) {
        setChecking(false);
      }
    }

    void pollOnce();
    const interval = window.setInterval(() => {
      void pollOnce();
    }, POLL_MS);

    const softTimer = window.setTimeout(() => {
      if (!cancelled) setChecking(false);
    }, SOFT_TIMEOUT_MS);

    void waitForRuntime(45_000, POLL_MS).then((ok) => {
      if (cancelled) return;
      if (ok) setChecking(false);
    });

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.clearTimeout(softTimer);
    };
  }, [attempt]);

  const value = useMemo(
    () => ({
      cloudReady,
      sidecarReady,
      ready: cloudReady && sidecarReady,
      checking,
      retry: () => setAttempt((n) => n + 1),
    }),
    [cloudReady, sidecarReady, checking],
  );

  return (
    <RuntimeStatusContext.Provider value={value}>
      {children}
    </RuntimeStatusContext.Provider>
  );
}

export function useRuntimeStatus(): RuntimeStatus {
  const ctx = useContext(RuntimeStatusContext);
  if (!ctx) {
    throw new Error("useRuntimeStatus must be used within RuntimeStatusProvider");
  }
  return ctx;
}
