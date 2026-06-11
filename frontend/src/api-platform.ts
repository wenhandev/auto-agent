import type {
  ChatMessageOut,
  ChatTurnRequest,
  ChatTurnResponse,
  CredentialCreate,
  CredentialListItem,
  CredentialOut,
  CredentialUpdate,
  LlmConfigOut,
  LlmConfigUpsert,
  LlmEffectiveOut,
  RunCreate,
  RunListItem,
  RunOut,
  RunReplayResponse,
  TriggerCreate,
  TriggerOut,
  TriggerUpdate,
  WorkflowCreate,
  WorkflowListItem,
  WorkflowOut,
  WorkflowUpdate,
  WorkflowVersionOut,
} from "./types-platform";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API request failed: ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseBody(res: Response): Promise<unknown> {
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  try {
    return await res.text();
  } catch {
    return null;
  }
}

async function http<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  if (!res.ok) {
    const errBody = await parseBody(res);
    throw new ApiError(res.status, errBody, `${method} ${path} -> ${res.status}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  const data = await parseBody(res);
  return data as T;
}

export interface WorkflowsApi {
  list(): Promise<WorkflowListItem[]>;
  create(body: WorkflowCreate): Promise<WorkflowOut>;
  get(workflowId: string): Promise<WorkflowOut>;
  update(workflowId: string, body: WorkflowUpdate): Promise<WorkflowOut>;
  remove(workflowId: string): Promise<void>;
  listVersions(workflowId: string): Promise<WorkflowVersionOut[]>;
  listCredentials(workflowId: string): Promise<CredentialListItem[]>;
  linkCredential(
    workflowId: string,
    credentialId: string,
  ): Promise<CredentialListItem>;
  unlinkCredential(
    workflowId: string,
    credentialId: string,
  ): Promise<void>;
}

export interface ChatApi {
  getHistory(sessionId: string): Promise<ChatMessageOut[]>;
  postMessage(
    sessionId: string,
    body: ChatTurnRequest,
  ): Promise<ChatTurnResponse>;
}

export interface RunsApi {
  list(workflowId?: string): Promise<RunListItem[]>;
  create(workflowId: string, body?: RunCreate): Promise<RunOut>;
  get(runId: string): Promise<RunReplayResponse>;
  abort(runId: string): Promise<RunOut>;
  replay(runId: string): Promise<RunReplayResponse>;
}

export interface CredentialsApi {
  list(): Promise<CredentialListItem[]>;
  create(body: CredentialCreate): Promise<CredentialOut>;
  get(credentialId: string): Promise<CredentialOut>;
  update(
    credentialId: string,
    body: CredentialUpdate,
  ): Promise<CredentialOut>;
  remove(credentialId: string): Promise<void>;
}

export interface LlmConfigTestResult {
  ok: boolean;
  message?: string | null;
  error?: string | null;
}

export interface LlmConfigApi {
  list(): Promise<LlmConfigOut[]>;
  upsert(body: LlmConfigUpsert): Promise<LlmConfigOut>;
  activate(configId: string): Promise<LlmConfigOut>;
  remove(configId: string): Promise<void>;
  effective(): Promise<LlmEffectiveOut>;
  test(body: LlmConfigUpsert): Promise<LlmConfigTestResult>;
}

export interface TriggersApi {
  list(workflowId: string): Promise<TriggerOut[]>;
  create(workflowId: string, body: TriggerCreate): Promise<TriggerOut>;
  update(triggerId: string, body: TriggerUpdate): Promise<TriggerOut>;
  remove(triggerId: string): Promise<void>;
}

export interface ApiClient {
  workflows: WorkflowsApi;
  chat: ChatApi;
  runs: RunsApi;
  credentials: CredentialsApi;
  llmConfig: LlmConfigApi;
  triggers: TriggersApi;
}

export const apiClient: ApiClient = {
  workflows: {
    list: () => http<WorkflowListItem[]>("GET", "/api/workflows"),
    create: (body) => http<WorkflowOut>("POST", "/api/workflows", body),
    get: (workflowId) =>
      http<WorkflowOut>("GET", `/api/workflows/${encodeURIComponent(workflowId)}`),
    update: (workflowId, body) =>
      http<WorkflowOut>(
        "PUT",
        `/api/workflows/${encodeURIComponent(workflowId)}`,
        body,
      ),
    remove: (workflowId) =>
      http<void>(
        "DELETE",
        `/api/workflows/${encodeURIComponent(workflowId)}`,
      ),
    listVersions: (workflowId) =>
      http<WorkflowVersionOut[]>(
        "GET",
        `/api/workflows/${encodeURIComponent(workflowId)}/versions`,
      ),
    listCredentials: (workflowId) =>
      http<CredentialListItem[]>(
        "GET",
        `/api/workflows/${encodeURIComponent(workflowId)}/credentials`,
      ),
    linkCredential: (workflowId, credentialId) =>
      http<CredentialListItem>(
        "POST",
        `/api/workflows/${encodeURIComponent(workflowId)}/credentials`,
        { credential_id: credentialId },
      ),
    unlinkCredential: (workflowId, credentialId) =>
      http<void>(
        "DELETE",
        `/api/workflows/${encodeURIComponent(workflowId)}/credentials/${encodeURIComponent(credentialId)}`,
      ),
  },
  chat: {
    getHistory: (sessionId) =>
      http<ChatMessageOut[]>(
        "GET",
        `/api/chat/${encodeURIComponent(sessionId)}`,
      ),
    postMessage: (sessionId, body) =>
      http<ChatTurnResponse>(
        "POST",
        `/api/chat/${encodeURIComponent(sessionId)}/messages`,
        body,
      ),
  },
  runs: {
    list: (workflowId) => {
      const qs = workflowId
        ? `?workflow_id=${encodeURIComponent(workflowId)}`
        : "";
      return http<RunListItem[]>("GET", `/api/runs${qs}`);
    },
    create: (workflowId, body) =>
      http<RunOut>("POST", "/api/runs", {
        workflow_id: workflowId,
        ...(body ?? {}),
      }),
    get: (runId) =>
      http<RunReplayResponse>("GET", `/api/runs/${encodeURIComponent(runId)}`),
    abort: (runId) =>
      http<RunOut>("POST", `/api/runs/${encodeURIComponent(runId)}/abort`),
    replay: (runId) =>
      http<RunReplayResponse>("GET", `/api/runs/${encodeURIComponent(runId)}`),
  },
  credentials: {
    list: () => http<CredentialListItem[]>("GET", "/api/credentials"),
    create: (body) => http<CredentialOut>("POST", "/api/credentials", body),
    get: (credentialId) =>
      http<CredentialOut>(
        "GET",
        `/api/credentials/${encodeURIComponent(credentialId)}`,
      ),
    update: (credentialId, body) =>
      http<CredentialOut>(
        "PUT",
        `/api/credentials/${encodeURIComponent(credentialId)}`,
        body,
      ),
    remove: (credentialId) =>
      http<void>(
        "DELETE",
        `/api/credentials/${encodeURIComponent(credentialId)}`,
      ),
  },
  llmConfig: {
    list: () => http<LlmConfigOut[]>("GET", "/api/llm-config"),
    upsert: (body) => http<LlmConfigOut>("POST", "/api/llm-config", body),
    activate: (configId) =>
      http<LlmConfigOut>(
        "POST",
        `/api/llm-config/${encodeURIComponent(configId)}/activate`,
      ),
    remove: (configId) =>
      http<void>(
        "DELETE",
        `/api/llm-config/${encodeURIComponent(configId)}`,
      ),
    effective: () => http<LlmEffectiveOut>("GET", "/api/llm-config/effective"),
    test: (body) =>
      http<LlmConfigTestResult>("POST", "/api/llm-config/test", body),
  },
  triggers: {
    list: (workflowId) =>
      http<TriggerOut[]>(
        "GET",
        `/api/workflows/${encodeURIComponent(workflowId)}/triggers`,
      ),
    create: (workflowId, body) =>
      http<TriggerOut>(
        "POST",
        `/api/workflows/${encodeURIComponent(workflowId)}/triggers`,
        body,
      ),
    update: (triggerId, body) =>
      http<TriggerOut>(
        "PATCH",
        `/api/triggers/${encodeURIComponent(triggerId)}`,
        body,
      ),
    remove: (triggerId) =>
      http<void>(
        "DELETE",
        `/api/triggers/${encodeURIComponent(triggerId)}`,
      ),
  },
};
