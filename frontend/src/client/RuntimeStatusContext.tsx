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
  fetchRuntimeHealth,
  waitForRuntime,
} from "./api";
import { desktopDefaultCloudUrl, isDesktopCloudUrlBakedIn } from "./cloudUrl";

interface RuntimeStatus {
  cloudReady: boolean;
  runtimeReady: boolean;
  ready: boolean;
  checking: boolean;
  retry: () => void;
}

const RuntimeStatusContext = createContext<RuntimeStatus | null>(null);

const POLL_MS = 500;
const SOFT_TIMEOUT_MS = 8_000;

export function RuntimeStatusProvider({ children }: { children: ReactNode }) {
  const [cloudReady, setCloudReady] = useState(false);
  const [runtimeReady, setRuntimeReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const cloudUrl = desktopDefaultCloudUrl();
    setChecking(true);
    setCloudReady(false);
    setRuntimeReady(false);

    async function pollOnce() {
      const [cloud, runtime] = await Promise.all([
        fetchCloudHealth(cloudUrl),
        fetchRuntimeHealth(),
      ]);
      if (cancelled) return;
      setCloudReady(cloud);
      setRuntimeReady(runtime);
      const startupComplete = isDesktopCloudUrlBakedIn() ? runtime : cloud && runtime;
      if (startupComplete) {
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

    if (isDesktopCloudUrlBakedIn()) {
      void waitForRuntime(45_000, POLL_MS).then((ok) => {
        if (cancelled) return;
        if (ok) setChecking(false);
      });
    } else {
      void waitForRuntime(45_000, POLL_MS, cloudUrl).then((ok) => {
        if (cancelled) return;
        if (ok) setChecking(false);
      });
    }

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.clearTimeout(softTimer);
    };
  }, [attempt]);

  const production = isDesktopCloudUrlBakedIn();
  const value = useMemo(
    () => ({
      cloudReady,
      runtimeReady,
      ready: production ? runtimeReady : cloudReady && runtimeReady,
      checking,
      retry: () => setAttempt((n) => n + 1),
    }),
    [cloudReady, runtimeReady, checking, production],
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
