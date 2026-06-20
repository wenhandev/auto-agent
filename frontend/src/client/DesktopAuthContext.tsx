import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { workerLogin, fetchWorkerMe, clearSidecarSession, syncSidecarSession } from "./api";
import { configureCloudApi } from "./cloudApi";
import {
  clearSession,
  loadSession,
  saveSession,
  updateApprovalStatus,
} from "./session";
import type { DesktopSession } from "./types";

interface DesktopAuthContextValue {
  session: DesktopSession | null;
  isLoading: boolean;
  login: (params: {
    cloudUrl: string;
    email: string;
    password: string;
    displayName?: string;
    tags?: string[];
  }) => Promise<void>;
  logout: () => void;
  refreshApproval: () => Promise<void>;
  updateProfile: (patch: { displayName?: string; tags?: string[] }) => void;
}

const DesktopAuthContext = createContext<DesktopAuthContextValue | null>(null);

export function DesktopAuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<DesktopSession | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const saved = loadSession();
    setSession(saved);
    configureCloudApi(saved);
    if (saved) {
      void syncSidecarSession(saved).catch(() => {
        // runtime may not be ready yet; RuntimeGate handles startup
      });
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(
    async (params: {
      cloudUrl: string;
      email: string;
      password: string;
      displayName?: string;
      tags?: string[];
    }) => {
      const next = await workerLogin(params);
      saveSession(next);
      configureCloudApi(next);
      setSession(next);
    },
    [],
  );

  const logout = useCallback(() => {
    void clearSidecarSession();
    clearSession();
    configureCloudApi(null);
    setSession(null);
  }, []);

  const refreshApproval = useCallback(async () => {
    const current = loadSession();
    if (!current) return;
    const me = await fetchWorkerMe(current);
    updateApprovalStatus(me.approval_status);
    const next = { ...current, approvalStatus: me.approval_status };
    saveSession(next);
    setSession(next);
  }, []);

  const updateProfile = useCallback(
    (patch: { displayName?: string; tags?: string[] }) => {
      const current = loadSession();
      if (!current) return;
      const next: DesktopSession = {
        ...current,
        displayName: patch.displayName ?? current.displayName,
        tags: patch.tags ?? current.tags,
      };
      saveSession(next);
      setSession(next);
    },
    [],
  );

  const value = useMemo(
    () => ({
      session,
      isLoading,
      login,
      logout,
      refreshApproval,
      updateProfile,
    }),
    [session, isLoading, login, logout, refreshApproval, updateProfile],
  );

  return (
    <DesktopAuthContext.Provider value={value}>
      {children}
    </DesktopAuthContext.Provider>
  );
}

export function useDesktopAuth(): DesktopAuthContextValue {
  const ctx = useContext(DesktopAuthContext);
  if (!ctx) {
    throw new Error("useDesktopAuth must be used within DesktopAuthProvider");
  }
  return ctx;
}
