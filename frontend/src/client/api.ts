import type {
  CloudWorkflowListItem,
  DesktopSession,
  LlmSettings,
  LocalRunMeta,
  SidecarStatus,
  WorkerLoginResponse,
  WorkerMeResponse,
  WorkflowDraftMeta,
} from "./types";
import {
  desktopDefaultCloudUrl,
  isDesktopCloudUrlBakedIn,
  isLocalDevCloudUrl,
} from "./cloudUrl";
import { getOrCreateMachineId, loadSession } from "./session";
import { isTauriShell } from "./tauriShell";
import {
  fetchRuntimeHealth as probeRuntimeHealth,
  runtimeFetch,
  runtimeStreamUrl,
} from "./runtimeBridge";

const DEFAULT_CLOUD_URL = desktopDefaultCloudUrl();
const AGENT_VERSION = "0.1.0";
const RUNTIME_SYNC_RETRY_MS = 2_000;
const RUNTIME_SYNC_MAX_ATTEMPTS = 30;

export class DesktopApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "DesktopApiError";
  }
}

async function desktopFetch(url: string, init?: RequestInit): Promise<Response> {
  if (isTauriShell()) {
    const { fetch: tauriFetch } = await import("@tauri-apps/plugin-http");
    return tauriFetch(url, init);
  }
  return fetch(url, init);
}

function isNetworkFetchFailure(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const message = err.message.toLowerCase();
  return (
    message === "load failed" ||
    message.includes("failed to fetch") ||
    message.includes("networkerror") ||
    message.includes("network request failed") ||
    message.includes("error sending request")
  );
}

function toDesktopNetworkError(
  err: unknown,
  context: string,
  url?: string,
): DesktopApiError {
  if (err instanceof DesktopApiError) return err;
  if (isNetworkFetchFailure(err)) {
    const target = url ? ` (${url})` : "";
    return new DesktopApiError(`${context}${target}`, 0);
  }
  const detail = err instanceof Error ? err.message : String(err);
  const target = url ? ` (${url})` : "";
  return new DesktopApiError(`${context}: ${detail}${target}`, 0);
}

function cloudApiRoot(cloudUrl: string): string {
  const normalized = cloudUrl.trim().replace(/\/$/, "");
  const proxyTarget = (
    import.meta.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001"
  ).replace(/\/$/, "");
  if (import.meta.env.DEV && normalized === proxyTarget) {
    return "";
  }
  return normalized;
}

function defaultHostname(): string {
  if (isTauriShell()) {
    return "My device";
  }
  if (typeof window !== "undefined" && window.location?.hostname) {
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") {
      return host;
    }
  }
  return "desktop";
}

function shouldUseDirectCloudApi(cloudUrl: string): boolean {
  return isDesktopCloudUrlBakedIn() || !isLocalDevCloudUrl(cloudUrl);
}

function parseApiErrorDetail(text: string, fallback: string): string {
  const trimmed = text.trim();
  if (!trimmed) return fallback;
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; message?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail) return parsed.detail;
    if (typeof parsed.message === "string" && parsed.message) return parsed.message;
  } catch {
    // keep raw text
  }
  return trimmed;
}

export function isSessionAuthError(err: unknown): boolean {
  if (!(err instanceof DesktopApiError)) return false;
  if (err.status === 401) return true;
  const msg = err.message.toLowerCase();
  return msg.includes("invalid session") || msg.includes("not signed in");
}

function normalizeSessionAuthError(detail: string, status: number): string {
  if (status !== 401 && !detail.toLowerCase().includes("invalid session")) {
    return detail;
  }
  return "Cloud sign-in session expired. Sign out and sign in again.";
}

async function cloudDirectFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const session = loadSession();
  if (!session?.webSessionToken) {
    throw new DesktopApiError("Not signed in", 401);
  }
  const root = cloudApiRoot(session.cloudUrl);
  const url = `${root}${path}`;
  let res: Response;
  try {
    res = await desktopFetch(url, {
      ...init,
      headers: {
        Authorization: `Bearer ${session.webSessionToken}`,
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    throw toDesktopNetworkError(err, "Could not reach the cloud server.", url);
  }
  if (!res.ok) {
    const text = await res.text();
    const detail = parseApiErrorDetail(text, res.statusText);
    throw new DesktopApiError(normalizeSessionAuthError(detail, res.status), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function runtimeJsonFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await runtimeFetch(path, init);
  } catch (err) {
    throw toDesktopNetworkError(
      err,
      "Auto Agent runtime is unavailable. Quit and reopen the app, or click Retry on the startup banner.",
    );
  }
  if (!res.ok) {
    const text = await res.text();
    const detail = parseApiErrorDetail(text, res.statusText);
    throw new DesktopApiError(normalizeSessionAuthError(detail, res.status), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function collectEnvironment(_cloudUrl: string): Promise<Record<string, unknown>> {
  try {
    return await runtimeJsonFetch<Record<string, unknown>>("/doctor");
  } catch {
    return {
      environment_status: "unknown",
      checks: [],
      capabilities: {
        platform: typeof navigator !== "undefined" ? navigator.platform : "desktop",
        arch: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
        agent_version: AGENT_VERSION,
      },
    };
  }
}

async function cloudWebLogin(
  cloudUrl: string,
  email: string,
  password: string,
): Promise<string> {
  const root = cloudApiRoot(cloudUrl);
  let res: Response;
  const loginUrl = `${root}/api/auth/login`;
  try {
    res = await desktopFetch(loginUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    });
  } catch (err) {
    throw toDesktopNetworkError(
      err,
      "Could not reach the cloud server to sign in. Check your internet connection",
      loginUrl,
    );
  }
  if (!res.ok) {
    const text = await res.text();
    throw new DesktopApiError(text || res.statusText, res.status);
  }
  const data = (await res.json()) as { token: string };
  return data.token;
}

export function getDesktopOAuthStartUrl(cloudUrl: string, provider: "google"): string {
  const root = cloudApiRoot(cloudUrl);
  return `${root}/api/auth/oauth/${provider}/start?client=desktop`;
}

export async function workerLogin(params: {
  cloudUrl: string;
  email: string;
  password: string;
  displayName?: string;
  tags?: string[];
}): Promise<DesktopSession> {
  const cloudUrl = params.cloudUrl.trim().replace(/\/$/, "");
  const apiRoot = cloudApiRoot(cloudUrl);
  const environment = await collectEnvironment(cloudUrl);
  const payload = {
    email: params.email.trim(),
    password: params.password,
    machine_id: getOrCreateMachineId(),
    display_name:
      params.displayName?.trim() ||
      params.email.split("@")[0]?.trim() ||
      defaultHostname(),
    hostname: defaultHostname(),
    tags: params.tags?.length ? params.tags : ["default"],
    agent_version: AGENT_VERSION,
    environment,
  };
  const workerLoginUrl = `${apiRoot}/api/v1/workers/login`;
  const [workerRes, webToken] = await Promise.all([
    desktopFetch(workerLoginUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch((err) => {
      throw toDesktopNetworkError(
        err,
        "Could not reach the cloud server to register this device",
        workerLoginUrl,
      );
    }),
    cloudWebLogin(cloudUrl, params.email, params.password),
  ]);
  if (!workerRes.ok) {
    const text = await workerRes.text();
    throw new DesktopApiError(text || workerRes.statusText, workerRes.status);
  }
  const data = (await workerRes.json()) as WorkerLoginResponse;
  const session: DesktopSession = {
    cloudUrl,
    workerSessionToken: data.worker_session_token,
    webSessionToken: webToken,
    workerId: data.worker_id,
    orgId: data.org_id,
    approvalStatus: data.approval_status,
    machineId: payload.machine_id,
    displayName: payload.display_name,
    tags: payload.tags,
  };
  scheduleRuntimeSync(session);
  return session;
}

export async function workerLoginOAuth(params: {
  cloudUrl: string;
  oauthExchangeCode: string;
  displayName?: string;
  tags?: string[];
}): Promise<DesktopSession> {
  const cloudUrl = params.cloudUrl.trim().replace(/\/$/, "");
  const apiRoot = cloudApiRoot(cloudUrl);
  const environment = await collectEnvironment(cloudUrl);

  const exchangeUrl = `${apiRoot}/api/auth/oauth/exchange`;
  let exchangeRes: Response;
  try {
    exchangeRes = await desktopFetch(exchangeUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: params.oauthExchangeCode }),
    });
  } catch (err) {
    throw toDesktopNetworkError(
      err,
      "Could not reach the cloud server to complete sign-in. Check your internet connection",
      exchangeUrl,
    );
  }
  if (!exchangeRes.ok) {
    const text = await exchangeRes.text();
    throw new DesktopApiError(text || exchangeRes.statusText, exchangeRes.status);
  }
  const exchangeData = (await exchangeRes.json()) as { token: string };
  const webToken = exchangeData.token;

  const payload = {
    session_token: webToken,
    machine_id: getOrCreateMachineId(),
    display_name: params.displayName?.trim() || defaultHostname(),
    hostname: defaultHostname(),
    tags: params.tags?.length ? params.tags : ["default"],
    agent_version: AGENT_VERSION,
    environment,
  };
  const workerOAuthUrl = `${apiRoot}/api/v1/workers/login/oauth`;
  let workerRes: Response;
  try {
    workerRes = await desktopFetch(workerOAuthUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    throw toDesktopNetworkError(
      err,
      "Could not reach the cloud server to register this device as a worker",
      workerOAuthUrl,
    );
  }
  if (!workerRes.ok) {
    const text = await workerRes.text();
    throw new DesktopApiError(text || workerRes.statusText, workerRes.status);
  }
  const data = (await workerRes.json()) as WorkerLoginResponse;
  const session: DesktopSession = {
    cloudUrl,
    workerSessionToken: data.worker_session_token,
    webSessionToken: webToken,
    workerId: data.worker_id,
    orgId: data.org_id,
    approvalStatus: data.approval_status,
    machineId: payload.machine_id,
    displayName: payload.display_name,
    tags: payload.tags,
  };

  scheduleRuntimeSync(session);
  return session;
}

const BAKED_IN_OAUTH_FALLBACK: {
  providers: string[];
  password_login_enabled: boolean;
} = {
  providers: ["google"],
  password_login_enabled: false,
};

export async function fetchOAuthProviders(
  cloudUrl: string,
): Promise<{ providers: string[]; password_login_enabled: boolean }> {
  const root = cloudApiRoot(cloudUrl);
  try {
    const res = await desktopFetch(`${root}/api/auth/oauth/providers`);
    if (!res.ok) {
      throw new DesktopApiError(
        `Failed to load sign-in options (${res.status})`,
        res.status,
      );
    }
    return (await res.json()) as {
      providers: string[];
      password_login_enabled: boolean;
    };
  } catch (err) {
    if (isDesktopCloudUrlBakedIn()) {
      return { ...BAKED_IN_OAUTH_FALLBACK };
    }
    throw err instanceof DesktopApiError
      ? err
      : new DesktopApiError(
          err instanceof Error ? err.message : "Failed to load sign-in options",
          0,
        );
  }
}

/** Retry runtime session sync in the background; login does not wait on the runtime. */
export function scheduleRuntimeSync(session: DesktopSession): void {
  void (async () => {
    for (let attempt = 0; attempt < RUNTIME_SYNC_MAX_ATTEMPTS; attempt += 1) {
      if (await fetchRuntimeHealth()) {
        try {
          await syncRuntimeSession(session);
          return;
        } catch {
          // runtime up but session sync failed — retry
        }
      }
      await new Promise((r) => setTimeout(r, RUNTIME_SYNC_RETRY_MS));
    }
  })();
}

/** @deprecated use scheduleRuntimeSync */
export const scheduleSidecarSync = scheduleRuntimeSync;

export async function syncRuntimeSession(session: DesktopSession): Promise<void> {
  await runtimeJsonFetch("/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      cloud_url: session.cloudUrl,
      worker_session_token: session.workerSessionToken,
      web_session_token: session.webSessionToken,
      worker_id: session.workerId,
      org_id: session.orgId,
    }),
  });
}

/** @deprecated use syncRuntimeSession */
export const syncSidecarSession = syncRuntimeSession;

export async function clearRuntimeSession(): Promise<void> {
  try {
    await runtimeFetch("/session", { method: "DELETE" });
  } catch {
    // runtime may already be stopped
  }
}

/** @deprecated use clearRuntimeSession */
export const clearSidecarSession = clearRuntimeSession;

export async function fetchWorkerMe(session: DesktopSession): Promise<WorkerMeResponse> {
  const root = cloudApiRoot(session.cloudUrl);
  let res: Response;
  try {
    res = await desktopFetch(`${root}/api/v1/workers/me`, {
      headers: { Authorization: `Bearer ${session.workerSessionToken}` },
    });
  } catch (err) {
    throw toDesktopNetworkError(
      err,
      "Could not reach the cloud server to refresh worker status.",
    );
  }
  if (!res.ok) {
    const text = await res.text();
    throw new DesktopApiError(text || res.statusText, res.status);
  }
  return (await res.json()) as WorkerMeResponse;
}

export async function fetchRuntimeHealth(): Promise<boolean> {
  return probeRuntimeHealth();
}

/** @deprecated use fetchRuntimeHealth */
export const fetchSidecarHealth = fetchRuntimeHealth;

export async function fetchRuntimeStatus(): Promise<SidecarStatus | null> {
  try {
    return await runtimeJsonFetch<SidecarStatus>("/status");
  } catch {
    return null;
  }
}

/** @deprecated use fetchRuntimeStatus */
export const fetchSidecarStatus = fetchRuntimeStatus;

export async function fetchCloudHealth(
  cloudUrl = DEFAULT_CLOUD_URL,
): Promise<boolean> {
  try {
    const root = cloudApiRoot(cloudUrl);
    const res = await desktopFetch(`${root}/api/health`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { ok?: boolean };
    return data.ok === true;
  } catch {
    return false;
  }
}

export async function waitForRuntimeHealth(
  timeoutMs = 30_000,
  intervalMs = 500,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await fetchRuntimeHealth()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

/** @deprecated use waitForRuntimeHealth */
export const waitForSidecarHealth = waitForRuntimeHealth;

export async function waitForRuntime(
  timeoutMs = 45_000,
  intervalMs = 500,
  cloudUrl = DEFAULT_CLOUD_URL,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const [runtime, cloud] = await Promise.all([
      fetchRuntimeHealth(),
      fetchCloudHealth(cloudUrl),
    ]);
    if (runtime && cloud) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

export async function fetchCloudWorkflows(): Promise<CloudWorkflowListItem[]> {
  const session = loadSession();
  if (!session?.webSessionToken) {
    throw new DesktopApiError(
      "Cloud sign-in session expired. Sign out and sign in again.",
      401,
    );
  }
  if (shouldUseDirectCloudApi(session.cloudUrl)) {
    return cloudDirectFetch<CloudWorkflowListItem[]>("/api/workflows");
  }
  return runtimeJsonFetch("/cloud/workflows");
}

export async function fetchCloudWorkflow(workflowId: string): Promise<unknown> {
  const session = loadSession();
  if (!session?.webSessionToken) {
    throw new DesktopApiError(
      "Cloud sign-in session expired. Sign out and sign in again.",
      401,
    );
  }
  if (shouldUseDirectCloudApi(session.cloudUrl)) {
    return cloudDirectFetch(`/api/workflows/${encodeURIComponent(workflowId)}`);
  }
  return runtimeJsonFetch(`/cloud/workflows/${encodeURIComponent(workflowId)}`);
}

export async function pullCloudWorkflow(workflowId: string): Promise<WorkflowDraftMeta> {
  const session = loadSession();
  if (!session?.webSessionToken) {
    throw new DesktopApiError(
      "Cloud sign-in session expired. Sign out and sign in again.",
      401,
    );
  }
  if (shouldUseDirectCloudApi(session.cloudUrl)) {
    const data = (await cloudDirectFetch<{
      name?: string;
      current_version?: { workflow?: Record<string, unknown> };
    }>(`/api/workflows/${encodeURIComponent(workflowId)}`)) as {
      name?: string;
      current_version?: { workflow?: Record<string, unknown> };
    };
    const workflow = data.current_version?.workflow;
    if (!workflow || typeof workflow !== "object") {
      throw new DesktopApiError("Workflow has no current version", 404);
    }
    return runtimeJsonFetch<WorkflowDraftMeta>("/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_json: workflow,
        workflow_id: workflowId,
        name: data.name || workflowId,
      }),
    });
  }
  return runtimeJsonFetch(`/cloud/workflows/${encodeURIComponent(workflowId)}/pull`, {
    method: "POST",
  });
}

export async function listDrafts(): Promise<WorkflowDraftMeta[]> {
  return runtimeJsonFetch("/drafts");
}

export async function listLocalRuns(): Promise<LocalRunMeta[]> {
  return runtimeJsonFetch("/runs");
}

export async function fetchLocalRun(runId: string): Promise<LocalRunMeta> {
  return runtimeJsonFetch(`/runs/${encodeURIComponent(runId)}`);
}

export async function startLocalRun(body: {
  workflow_id?: string;
  workflow?: unknown;
  parameters?: Record<string, unknown>;
}): Promise<LocalRunMeta> {
  return runtimeJsonFetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function abortLocalRun(runId: string): Promise<void> {
  await runtimeJsonFetch(`/runs/${encodeURIComponent(runId)}/abort`, { method: "POST" });
}

export async function localRunEventsUrl(runId: string): Promise<string> {
  return runtimeStreamUrl(`/runs/${encodeURIComponent(runId)}/events`);
}

export async function localStreamWsUrl(runId: string): Promise<string> {
  const httpUrl = await runtimeStreamUrl(
    `/ws/stream/${encodeURIComponent(runId)}`,
  );
  return httpUrl.replace(/^http/, "ws");
}

export async function fetchLlmSettings(): Promise<LlmSettings> {
  return runtimeJsonFetch("/settings/llm");
}

export async function saveLlmSettings(body: LlmSettings): Promise<LlmSettings> {
  return runtimeJsonFetch("/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export type ComputerUseSettings = {
  available: boolean;
  /** Empty when available; explains missing extras / unsupported platform. */
  reason?: string;
  platform: string;
  always_allowed: string[];
  system_permissions_hint: string;
};

export async function fetchComputerUseSettings(): Promise<ComputerUseSettings> {
  return runtimeJsonFetch("/settings/computer-use");
}

export async function saveComputerUseSettings(body: {
  allow_always?: string;
  revoke?: string;
}): Promise<ComputerUseSettings> {
  return runtimeJsonFetch("/settings/computer-use", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function saveDraft(body: {
  local_id?: string;
  draft_json: unknown;
  workflow_id?: string | null;
  name?: string;
  cloud_version_id?: string;
}): Promise<WorkflowDraftMeta> {
  return runtimeJsonFetch("/drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchDraft(localId: string): Promise<unknown> {
  return runtimeJsonFetch(`/drafts/${encodeURIComponent(localId)}`);
}

export async function publishDraft(
  localId: string,
): Promise<{ status: "published" | "queued"; detail?: string }> {
  const res = await runtimeFetch(
    `/drafts/${encodeURIComponent(localId)}/publish`,
    { method: "POST" },
  );
  const text = await res.text();
  let body: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>;
    if (parsed && typeof parsed === "object") body = parsed;
  } catch {
    // keep empty body
  }
  if (res.status === 202) {
    return {
      status: "queued",
      detail:
        typeof body.detail === "string"
          ? body.detail
          : "Publish queued for retry when online",
    };
  }
  if (!res.ok) {
    const detail =
      typeof body.detail === "string" ? body.detail : text || res.statusText;
    throw new DesktopApiError(detail, res.status);
  }
  return { status: "published" };
}
