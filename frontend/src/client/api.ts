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
import { getOrCreateMachineId } from "./session";

const SIDECAR_BASE = "http://127.0.0.1:3921";
const DEFAULT_CLOUD_URL =
  import.meta.env.VITE_CLOUD_URL || "http://127.0.0.1:8001";
const AGENT_VERSION = "0.1.0";

export class DesktopApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "DesktopApiError";
  }
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
  if (typeof window !== "undefined" && window.location?.hostname) {
    return window.location.hostname;
  }
  return "desktop";
}

async function sidecarFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${SIDECAR_BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    let detail = text || res.statusText;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      if (parsed.detail) detail = parsed.detail;
    } catch {
      // keep raw text
    }
    throw new DesktopApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function cloudWebLogin(
  cloudUrl: string,
  email: string,
  password: string,
): Promise<string> {
  const root = cloudApiRoot(cloudUrl);
  const res = await fetch(`${root}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email.trim(), password }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new DesktopApiError(text || res.statusText, res.status);
  }
  const data = (await res.json()) as { token: string };
  return data.token;
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
  const payload = {
    email: params.email.trim(),
    password: params.password,
    machine_id: getOrCreateMachineId(),
    display_name: params.displayName?.trim() || defaultHostname(),
    hostname: defaultHostname(),
    tags: params.tags?.length ? params.tags : ["default"],
    agent_version: AGENT_VERSION,
  };
  const [workerRes, webToken] = await Promise.all([
    fetch(`${apiRoot}/api/v1/workers/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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
  await syncSidecarSession(session);
  return session;
}

export async function syncSidecarSession(session: DesktopSession): Promise<void> {
  await sidecarFetch("/session", {
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

export async function clearSidecarSession(): Promise<void> {
  try {
    await fetch(`${SIDECAR_BASE}/session`, { method: "DELETE" });
  } catch {
    // sidecar may already be stopped
  }
}

export async function fetchWorkerMe(session: DesktopSession): Promise<WorkerMeResponse> {
  const res = await fetch(`${session.cloudUrl}/api/v1/workers/me`, {
    headers: { Authorization: `Bearer ${session.workerSessionToken}` },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new DesktopApiError(text || res.statusText, res.status);
  }
  return (await res.json()) as WorkerMeResponse;
}

export async function fetchSidecarHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${SIDECAR_BASE}/health`, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return false;
    const data = (await res.json()) as { status?: string };
    return data.status === "ok";
  } catch {
    return false;
  }
}

export async function fetchSidecarStatus(): Promise<SidecarStatus | null> {
  try {
    const res = await fetch(`${SIDECAR_BASE}/status`, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return null;
    return (await res.json()) as SidecarStatus;
  } catch {
    return null;
  }
}

export async function fetchCloudHealth(
  cloudUrl = DEFAULT_CLOUD_URL,
): Promise<boolean> {
  try {
    const root = cloudApiRoot(cloudUrl);
    const res = await fetch(`${root}/api/health`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { ok?: boolean };
    return data.ok === true;
  } catch {
    return false;
  }
}

export async function waitForSidecarHealth(
  timeoutMs = 30_000,
  intervalMs = 500,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await fetchSidecarHealth()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

export async function waitForRuntime(
  timeoutMs = 45_000,
  intervalMs = 500,
  cloudUrl = DEFAULT_CLOUD_URL,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const [sidecar, cloud] = await Promise.all([
      fetchSidecarHealth(),
      fetchCloudHealth(cloudUrl),
    ]);
    if (sidecar && cloud) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

export async function fetchCloudWorkflows(): Promise<CloudWorkflowListItem[]> {
  return sidecarFetch("/cloud/workflows");
}

export async function fetchCloudWorkflow(workflowId: string): Promise<unknown> {
  return sidecarFetch(`/cloud/workflows/${encodeURIComponent(workflowId)}`);
}

export async function pullCloudWorkflow(workflowId: string): Promise<WorkflowDraftMeta> {
  return sidecarFetch(`/cloud/workflows/${encodeURIComponent(workflowId)}/pull`, {
    method: "POST",
  });
}

export async function listDrafts(): Promise<WorkflowDraftMeta[]> {
  return sidecarFetch("/drafts");
}

export async function listLocalRuns(): Promise<LocalRunMeta[]> {
  return sidecarFetch("/runs");
}

export async function startLocalRun(body: {
  workflow_id?: string;
  workflow?: unknown;
  parameters?: Record<string, unknown>;
}): Promise<LocalRunMeta> {
  return sidecarFetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function abortLocalRun(runId: string): Promise<void> {
  await sidecarFetch(`/runs/${encodeURIComponent(runId)}/abort`, { method: "POST" });
}

export function localRunEventsUrl(runId: string): string {
  return `${SIDECAR_BASE}/runs/${encodeURIComponent(runId)}/events`;
}

export function localStreamWsUrl(runId: string): string {
  const base = SIDECAR_BASE.replace(/^http/, "ws");
  return `${base}/ws/stream/${encodeURIComponent(runId)}`;
}

export async function fetchLlmSettings(): Promise<LlmSettings> {
  return sidecarFetch("/settings/llm");
}

export async function saveLlmSettings(body: LlmSettings): Promise<LlmSettings> {
  return sidecarFetch("/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchDraft(localId: string): Promise<unknown> {
  return sidecarFetch(`/drafts/${encodeURIComponent(localId)}`);
}

export async function publishDraft(
  localId: string,
): Promise<{ status: "published" | "queued"; detail?: string }> {
  const res = await fetch(
    `${SIDECAR_BASE}/drafts/${encodeURIComponent(localId)}/publish`,
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
