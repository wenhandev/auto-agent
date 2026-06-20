import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/api-platform";
import type { LoginRequest, MeResponse } from "@/types-platform";

const AUTH_BYPASS = import.meta.env.VITE_AUTH_BYPASS === "true";
const QK_ME = ["auth", "me"] as const;

interface AuthContextValue {
  bypass: boolean;
  user: MeResponse | null;
  isPlatformAdmin: boolean;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (body: LoginRequest) => Promise<void>;
  oauthExchange: (code: string) => Promise<void>;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: QK_ME,
    queryFn: () => apiClient.auth.me(),
    enabled: !AUTH_BYPASS,
    retry: (count, err) => {
      if (err instanceof ApiError && err.status === 401) return false;
      return count < 1;
    },
    staleTime: 60_000,
  });

  const loginMut = useMutation({
    mutationFn: (body: LoginRequest) => apiClient.auth.login(body),
    onSuccess: (data) => {
      queryClient.setQueryData(QK_ME, data.user);
    },
  });

  const logoutMut = useMutation({
    mutationFn: () => apiClient.auth.logout(),
    onSuccess: () => {
      queryClient.setQueryData(QK_ME, null);
      void queryClient.invalidateQueries({ queryKey: QK_ME });
    },
  });

  const oauthExchangeMut = useMutation({
    mutationFn: (code: string) => apiClient.auth.oauthExchange(code),
    onSuccess: (data) => {
      queryClient.setQueryData(QK_ME, data.user);
    },
  });

  const login = useCallback(
    async (body: LoginRequest) => {
      await loginMut.mutateAsync(body);
    },
    [loginMut],
  );

  const oauthExchange = useCallback(
    async (code: string) => {
      await oauthExchangeMut.mutateAsync(code);
    },
    [oauthExchangeMut],
  );

  const logout = useCallback(async () => {
    await logoutMut.mutateAsync();
  }, [logoutMut]);

  const refetch = useCallback(async () => {
    await meQuery.refetch();
  }, [meQuery]);

  const value = useMemo<AuthContextValue>(() => {
    const user = AUTH_BYPASS ? null : (meQuery.data ?? null);
    const isAuthenticated = AUTH_BYPASS || !!user;
    return {
      bypass: AUTH_BYPASS,
      user,
      isPlatformAdmin: !!user?.is_platform_admin,
      isLoading: AUTH_BYPASS ? false : meQuery.isLoading,
      isAuthenticated,
      login,
      oauthExchange,
      logout,
      refetch,
    };
  }, [
    meQuery.data,
    meQuery.isLoading,
    login,
    oauthExchange,
    logout,
    refetch,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

export function isAuthBypassEnabled(): boolean {
  return AUTH_BYPASS;
}
