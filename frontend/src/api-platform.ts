import type {
  ApiKeyCreate,
  ApiKeyCreated,
  ApiKeyOut,
  ApprovalDecisionRequest,
  ApprovalDecisionResponse,
  BrowserProfileCreate,
  BrowserProfileOut,
  BrowserProfileUpdate,
  ChatMessageOut,
  ChatTurnRequest,
  ChatTurnResponse,
  CredentialCreate,
  CredentialListItem,
  CredentialOut,
  CredentialTypeSpec,
  CredentialUpdate,
  IntegrationDescriptor,
  LlmConfigOut,
  LlmConfigUpsert,
  LlmEffectiveOut,
  AntibotSettingsOut,
  RuntimeSettingsOut,
  LastOutputShapesResponse,
  PendingApprovalOut,
  RecordingCreate,
  RecordingDistillOut,
  RecordingGenerateOut,
  RecordingOut,
  RunArtifactOut,
  RunCreate,
  RunListItem,
  RunOut,
  RunReplayResponse,
  StagingFileOut,
  BrowserSessionCreate,
  BrowserSessionMemoryEntry,
  BrowserSessionOut,
  PickElementOut,
  PickerEnableOut,
  RouteSkillOut,
  RouteSkillProposalAdoptOut,
  RouteSkillProposalAdoptPreviewOut,
  RouteSkillProposalOut,
  RouteSkillBucketOut,
  AdminAuthSettingsOut,
  AdminDomainRuleOut,
  AdminOrgOut,
  AdminUserOut,
  LoginRequest,
  LoginResponse,
  MeResponse,
  TaskCreate,
  TaskDistillOut,
  TaskOut,
  TestSelectorOut,
  TriggerCreate,
  TriggerOut,
  TriggerUpdate,
  ExpressionPreviewRequest,
  ExpressionPreviewResponse,
  WebhookDeliveryOut,
  WebhookReplayResponse,
  WebhookSubscriptionCreate,
  WebhookSubscriptionOut,
  WebhookSubscriptionUpdate,
  WebhookTestResponse,
  OrgMemberInvite,
  OrgMemberOut,
  OrgMemberRoleUpdate,
  OrgSettingsOut,
  OrgSettingsUpdate,
  WorkerOut,
  WorkflowCreate,
  WorkflowListItem,
  WorkflowOut,
  WorkflowUpdate,
  WorkflowVersionCreate,
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

let _bearerToken: string | null = null;
let _apiBaseUrl: string | null = null;

/** Desktop shell: inject web session token for cloud API calls. */
export function setApiBearerToken(token: string | null): void {
  _bearerToken = token;
}

/** Desktop shell: prefix cloud API paths when not using the Vite dev proxy. */
export function setApiBaseUrl(baseUrl: string | null): void {
  _apiBaseUrl = baseUrl ? baseUrl.replace(/\/$/, "") : null;
}

function resolveApiPath(path: string): string {
  if (!_apiBaseUrl || !path.startsWith("/")) {
    return path;
  }
  return `${_apiBaseUrl}${path}`;
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

export async function http<T>(
  method: string,
  path: string,
  body?: unknown,
  opts?: { apiKey?: string | null },
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (opts?.apiKey) {
    headers.Authorization = `Bearer ${opts.apiKey}`;
  } else if (_bearerToken) {
    headers.Authorization = `Bearer ${_bearerToken}`;
  }
  const init: RequestInit = {
    method,
    credentials: "include",
    headers: Object.keys(headers).length > 0 ? headers : undefined,
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  const res = await fetch(resolveApiPath(path), init);
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

async function uploadForm<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  if (_bearerToken) {
    headers.Authorization = `Bearer ${_bearerToken}`;
  }
  const res = await fetch(resolveApiPath(path), {
    method: "POST",
    credentials: "include",
    headers: Object.keys(headers).length > 0 ? headers : undefined,
    body: form,
  });
  if (!res.ok) {
    const errBody = await parseBody(res);
    throw new ApiError(res.status, errBody, `POST ${path} -> ${res.status}`);
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
  createVersion(
    workflowId: string,
    body: WorkflowVersionCreate,
  ): Promise<WorkflowVersionOut>;
  listCredentials(workflowId: string): Promise<CredentialListItem[]>;
  linkCredential(
    workflowId: string,
    credentialId: string,
  ): Promise<CredentialListItem>;
  unlinkCredential(
    workflowId: string,
    credentialId: string,
  ): Promise<void>;
  getLastOutputShapes(workflowId: string): Promise<LastOutputShapesResponse>;
  uploadInputFile(
    workflowId: string,
    file: File,
  ): Promise<StagingFileOut>;
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
  listArtifacts(
    runId: string,
    opts?: { kind?: string; nodeId?: string },
  ): Promise<RunArtifactOut[]>;
  artifactUrl(runId: string, artifactId: string): string;
  artifactThumbnailUrl(runId: string, artifactId: string): string;
}

export interface ApprovalsApi {
  listPending(runId: string): Promise<PendingApprovalOut[]>;
  resolve(
    runId: string,
    nodeId: string,
    body: ApprovalDecisionRequest,
  ): Promise<ApprovalDecisionResponse>;
}

export interface BrowserProfilesApi {
  list(): Promise<BrowserProfileOut[]>;
  create(body: BrowserProfileCreate): Promise<BrowserProfileOut>;
  get(profileId: string): Promise<BrowserProfileOut>;
  update(
    profileId: string,
    body: BrowserProfileUpdate,
  ): Promise<BrowserProfileOut>;
  remove(profileId: string): Promise<void>;
  captureFromRun(profileId: string, runId: string): Promise<BrowserProfileOut>;
}

export interface RecordingsApi {
  list(): Promise<RecordingOut[]>;
  create(body?: RecordingCreate): Promise<RecordingOut>;
  get(recordingId: string): Promise<RecordingOut>;
  stop(recordingId: string): Promise<RecordingOut>;
  generate(recordingId: string): Promise<RecordingGenerateOut>;
  distill(
    recordingId: string,
    body?: { use_llm?: boolean },
  ): Promise<RecordingDistillOut>;
  liveEvents(recordingId: string): Promise<Record<string, unknown>[]>;
}

export interface RouteSkillProposalsApi {
  list(opts?: {
    source_type?: string;
    source_id?: string;
  }): Promise<RouteSkillProposalOut[]>;
  adoptPreview(proposalId: string): Promise<RouteSkillProposalAdoptPreviewOut>;
  adopt(proposalId: string): Promise<RouteSkillProposalAdoptOut>;
  dismiss(proposalId: string): Promise<RouteSkillProposalOut>;
}

export interface ApiKeysApi {
  list(): Promise<ApiKeyOut[]>;
  create(body: ApiKeyCreate): Promise<ApiKeyCreated>;
  remove(keyId: string): Promise<void>;
}

export interface WebhooksApi {
  listSubscriptions(): Promise<WebhookSubscriptionOut[]>;
  listSubscriptionsV1(apiKey: string): Promise<WebhookSubscriptionOut[]>;
  getSubscriptionV1(
    apiKey: string,
    subscriptionId: string,
  ): Promise<WebhookSubscriptionOut>;
  createSubscriptionV1(
    apiKey: string,
    body: WebhookSubscriptionCreate,
  ): Promise<WebhookSubscriptionOut>;
  updateSubscriptionV1(
    apiKey: string,
    subscriptionId: string,
    body: WebhookSubscriptionUpdate,
  ): Promise<WebhookSubscriptionOut>;
  removeSubscriptionV1(
    apiKey: string,
    subscriptionId: string,
  ): Promise<void>;
  testSubscriptionV1(
    apiKey: string,
    subscriptionId: string,
  ): Promise<WebhookTestResponse>;
  listDeliveriesV1(
    apiKey: string,
    opts?: { subscriptionId?: string; status?: string; limit?: number },
  ): Promise<WebhookDeliveryOut[]>;
  replayDeliveryV1(
    apiKey: string,
    deliveryId: string,
  ): Promise<WebhookReplayResponse>;
}

export interface OrgsApi {
  listMembers(orgId: string): Promise<OrgMemberOut[]>;
  inviteMember(orgId: string, body: OrgMemberInvite): Promise<OrgMemberOut>;
  updateMemberRole(
    orgId: string,
    userId: string,
    body: OrgMemberRoleUpdate,
  ): Promise<OrgMemberOut>;
  removeMember(orgId: string, userId: string): Promise<void>;
  getSettings(orgId: string): Promise<OrgSettingsOut>;
  updateSettings(
    orgId: string,
    body: OrgSettingsUpdate,
  ): Promise<OrgSettingsOut>;
}

export interface WorkersApi {
  list(): Promise<WorkerOut[]>;
  approve(workerId: string): Promise<WorkerOut>;
  reject(workerId: string): Promise<WorkerOut>;
  revoke(workerId: string): Promise<WorkerOut>;
}

export interface IntegrationsApi {
  list(): Promise<IntegrationDescriptor[]>;
  get(app: string): Promise<IntegrationDescriptor>;
}

export interface CredentialsApi {
  list(): Promise<CredentialListItem[]>;
  listTypes(): Promise<CredentialTypeSpec[]>;
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

export interface SettingsApi {
  antibot(): Promise<AntibotSettingsOut>;
  runtime(): Promise<RuntimeSettingsOut>;
}

export interface TriggersApi {
  list(workflowId: string): Promise<TriggerOut[]>;
  create(workflowId: string, body: TriggerCreate): Promise<TriggerOut>;
  update(triggerId: string, body: TriggerUpdate): Promise<TriggerOut>;
  remove(triggerId: string): Promise<void>;
}

export interface ExpressionsApi {
  preview(body: ExpressionPreviewRequest): Promise<ExpressionPreviewResponse>;
}

export interface AuthApi {
  login(body: LoginRequest): Promise<LoginResponse>;
  logout(): Promise<{ ok: boolean }>;
  me(): Promise<MeResponse>;
  oauthProviders(): Promise<{ providers: string[]; password_login_enabled: boolean }>;
  oauthExchange(code: string): Promise<LoginResponse>;
}

export function getOAuthStartUrl(provider: "google"): string {
  return resolveApiPath(`/api/auth/oauth/${provider}/start`);
}

export interface BrowserSessionsApi {
  list(): Promise<BrowserSessionOut[]>;
  create(body?: BrowserSessionCreate): Promise<BrowserSessionOut>;
  get(sessionId: string): Promise<BrowserSessionOut>;
  keepAlive(sessionId: string): Promise<BrowserSessionOut>;
  close(sessionId: string): Promise<BrowserSessionOut>;
  remove(sessionId: string): Promise<{ ok: boolean }>;
  getMemory(
    sessionId: string,
  ): Promise<{ session_id: string; entries: BrowserSessionMemoryEntry[] }>;
  clearMemory(
    sessionId: string,
  ): Promise<{ session_id: string; entries: BrowserSessionMemoryEntry[] }>;
  pickerEnable(
    sessionId: string,
    body?: { mode?: string },
  ): Promise<PickerEnableOut>;
  pickerDisable(sessionId: string, pickerToken: string): Promise<{ ok: boolean }>;
  navigate(
    sessionId: string,
    pickerToken: string,
    url: string,
  ): Promise<{ url: string; title: string }>;
  pickElement(
    sessionId: string,
    pickerToken: string,
    x: number,
    y: number,
  ): Promise<PickElementOut>;
  testSelector(
    sessionId: string,
    pickerToken: string,
    selector: string,
  ): Promise<TestSelectorOut>;
  screenshot(
    sessionId: string,
    pickerToken: string,
  ): Promise<{ blob: Blob; viewport: { width: number; height: number } }>;
}

export interface RouteSkillsApi {
  list(): Promise<RouteSkillOut[]>;
  buckets(): Promise<RouteSkillBucketOut[]>;
  update(
    skillId: string,
    body: { enabled?: boolean; prompt?: string; priority?: number },
  ): Promise<RouteSkillOut>;
}

export interface TasksApi {
  create(body: TaskCreate): Promise<TaskOut>;
  get(runId: string): Promise<TaskOut>;
  distillRouteSkills(runId: string): Promise<TaskDistillOut>;
}

export interface AdminApi {
  listOrgs(): Promise<AdminOrgOut[]>;
  createOrg(body: {
    name: string;
    desktop_client_policy?: string;
  }): Promise<AdminOrgOut>;
  updateOrg(
    orgId: string,
    body: { name?: string; desktop_client_policy?: string },
  ): Promise<AdminOrgOut>;
  listUsers(): Promise<AdminUserOut[]>;
  createUser(body: {
    email: string;
    password: string;
    name?: string;
    org_id: string;
    role?: string;
    is_platform_admin?: boolean;
  }): Promise<AdminUserOut>;
  updateUser(
    userId: string,
    body: {
      name?: string;
      is_platform_admin?: boolean;
      disabled?: boolean;
    },
  ): Promise<AdminUserOut>;
  resetPassword(userId: string, password: string): Promise<{ status: string }>;
  deleteUser(userId: string): Promise<void>;
  authSettings(): Promise<AdminAuthSettingsOut>;
  listDomainRules(): Promise<AdminDomainRuleOut[]>;
  createDomainRule(body: {
    domain: string;
    org_id: string;
    default_role?: string;
  }): Promise<AdminDomainRuleOut>;
  deleteDomainRule(ruleId: string): Promise<void>;
}

export interface ApiClient {
  auth: AuthApi;
  workflows: WorkflowsApi;
  chat: ChatApi;
  runs: RunsApi;
  approvals: ApprovalsApi;
  browserProfiles: BrowserProfilesApi;
  browserSessions: BrowserSessionsApi;
  routeSkills: RouteSkillsApi;
  routeSkillProposals: RouteSkillProposalsApi;
  recordings: RecordingsApi;
  tasks: TasksApi;
  integrations: IntegrationsApi;
  credentials: CredentialsApi;
  llmConfig: LlmConfigApi;
  settings: SettingsApi;
  triggers: TriggersApi;
  expressions: ExpressionsApi;
  apiKeys: ApiKeysApi;
  webhooks: WebhooksApi;
  orgs: OrgsApi;
  workers: WorkersApi;
  admin: AdminApi;
}

export const apiClient: ApiClient = {
  auth: {
    login: (body) => http<LoginResponse>("POST", "/api/auth/login", body),
    logout: () => http<{ ok: boolean }>("POST", "/api/auth/logout"),
    me: () => http<MeResponse>("GET", "/api/auth/me"),
    oauthProviders: () =>
      http<{ providers: string[]; password_login_enabled: boolean }>(
        "GET",
        "/api/auth/oauth/providers",
      ),
    oauthExchange: (code) =>
      http<LoginResponse>("POST", "/api/auth/oauth/exchange", { code }),
  },
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
    createVersion: (workflowId, body) =>
      http<WorkflowVersionOut>(
        "POST",
        `/api/workflows/${encodeURIComponent(workflowId)}/versions`,
        body,
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
    getLastOutputShapes: (workflowId) =>
      http<LastOutputShapesResponse>(
        "GET",
        `/api/workflows/${encodeURIComponent(workflowId)}/last-output-shapes`,
      ),
    uploadInputFile: (workflowId, file) => {
      const form = new FormData();
      form.append("file", file);
      return uploadForm<StagingFileOut>(
        `/api/workflows/${encodeURIComponent(workflowId)}/input-files`,
        form,
      );
    },
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
    listArtifacts: (runId, opts) => {
      const params = new URLSearchParams();
      if (opts?.kind) params.set("kind", opts.kind);
      if (opts?.nodeId) params.set("node_id", opts.nodeId);
      const qs = params.toString();
      return http<RunArtifactOut[]>(
        "GET",
        `/api/runs/${encodeURIComponent(runId)}/artifacts${qs ? `?${qs}` : ""}`,
      );
    },
    artifactUrl: (runId, artifactId) =>
      resolveApiPath(
        `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,
      ),
    artifactThumbnailUrl: (runId, artifactId) =>
      resolveApiPath(
        `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}/thumbnail`,
      ),
  },
  approvals: {
    listPending: (runId) =>
      http<PendingApprovalOut[]>(
        "GET",
        `/api/runs/${encodeURIComponent(runId)}/approvals`,
      ),
    resolve: (runId, nodeId, body) =>
      http<ApprovalDecisionResponse>(
        "POST",
        `/api/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(nodeId)}`,
        body,
      ),
  },
  browserProfiles: {
    list: () => http<BrowserProfileOut[]>("GET", "/api/browser-profiles"),
    create: (body) =>
      http<BrowserProfileOut>("POST", "/api/browser-profiles", body),
    get: (profileId) =>
      http<BrowserProfileOut>(
        "GET",
        `/api/browser-profiles/${encodeURIComponent(profileId)}`,
      ),
    update: (profileId, body) =>
      http<BrowserProfileOut>(
        "PATCH",
        `/api/browser-profiles/${encodeURIComponent(profileId)}`,
        body,
      ),
    remove: (profileId) =>
      http<void>(
        "DELETE",
        `/api/browser-profiles/${encodeURIComponent(profileId)}`,
      ),
    captureFromRun: (profileId, runId) =>
      http<BrowserProfileOut>(
        "POST",
        `/api/browser-profiles/${encodeURIComponent(profileId)}/capture-from-run/${encodeURIComponent(runId)}`,
      ),
  },
  recordings: {
    list: () => http<RecordingOut[]>("GET", "/api/recordings"),
    create: (body) =>
      http<RecordingOut>("POST", "/api/recordings", body ?? {}),
    get: (recordingId) =>
      http<RecordingOut>(
        "GET",
        `/api/recordings/${encodeURIComponent(recordingId)}`,
      ),
    stop: (recordingId) =>
      http<RecordingOut>(
        "POST",
        `/api/recordings/${encodeURIComponent(recordingId)}/stop`,
      ),
    generate: (recordingId) =>
      http<RecordingGenerateOut>(
        "POST",
        `/api/recordings/${encodeURIComponent(recordingId)}/generate`,
      ),
    distill: (recordingId, body) =>
      http<RecordingDistillOut>(
        "POST",
        `/api/recordings/${encodeURIComponent(recordingId)}/distill`,
        body ?? {},
      ),
    liveEvents: (recordingId) =>
      http<Record<string, unknown>[]>(
        "GET",
        `/api/recordings/${encodeURIComponent(recordingId)}/events/live`,
      ),
  },
  browserSessions: {
    list: () => http<BrowserSessionOut[]>("GET", "/api/browser-sessions"),
    create: (body) =>
      http<BrowserSessionOut>("POST", "/api/browser-sessions", body ?? {}),
    get: (sessionId) =>
      http<BrowserSessionOut>(
        "GET",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}`,
      ),
    keepAlive: (sessionId) =>
      http<BrowserSessionOut>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/keep-alive`,
      ),
    close: (sessionId) =>
      http<BrowserSessionOut>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/close`,
      ),
    remove: (sessionId) =>
      http<{ ok: boolean }>(
        "DELETE",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}`,
      ),
    getMemory: (sessionId) =>
      http<{ session_id: string; entries: BrowserSessionMemoryEntry[] }>(
        "GET",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/memory`,
      ),
    clearMemory: (sessionId) =>
      http<{ session_id: string; entries: BrowserSessionMemoryEntry[] }>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/memory/clear`,
      ),
    pickerEnable: (sessionId, body = { mode: "coordinate" }) =>
      http<PickerEnableOut>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/picker/enable`,
        body,
      ),
    pickerDisable: (sessionId, pickerToken: string) =>
      http<{ ok: boolean }>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/picker/disable`,
        { picker_token: pickerToken },
      ),
    navigate: (sessionId, pickerToken: string, url: string) =>
      http<{ url: string; title: string }>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/navigate`,
        { picker_token: pickerToken, url },
      ),
    pickElement: (sessionId, pickerToken: string, x: number, y: number) =>
      http<PickElementOut>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/pick-element`,
        { picker_token: pickerToken, x, y },
      ),
    testSelector: (sessionId, pickerToken: string, selector: string) =>
      http<TestSelectorOut>(
        "POST",
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/test-selector`,
        { picker_token: pickerToken, selector },
      ),
    screenshot: async (sessionId: string, pickerToken: string) => {
      const res = await fetch(
        `/api/browser-sessions/${encodeURIComponent(sessionId)}/screenshot?picker_token=${encodeURIComponent(pickerToken)}`,
        { credentials: "include" },
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new ApiError(res.status, errBody, `GET screenshot -> ${res.status}`);
      }
      const blob = await res.blob();
      const width = Number(res.headers.get("X-Viewport-Width") ?? 1280);
      const height = Number(res.headers.get("X-Viewport-Height") ?? 720);
      return { blob, viewport: { width, height } };
    },
  },
  routeSkills: {
    list: () => http<RouteSkillOut[]>("GET", "/api/route-skills"),
    buckets: () => http<RouteSkillBucketOut[]>("GET", "/api/route-skills/buckets"),
    update: (skillId, body) =>
      http<RouteSkillOut>(
        "PATCH",
        `/api/route-skills/${encodeURIComponent(skillId)}`,
        body,
      ),
  },
  routeSkillProposals: {
    list: (opts) => {
      const params = new URLSearchParams();
      if (opts?.source_type) params.set("source_type", opts.source_type);
      if (opts?.source_id) params.set("source_id", opts.source_id);
      const qs = params.toString();
      return http<RouteSkillProposalOut[]>(
        "GET",
        `/api/route-skill-proposals${qs ? `?${qs}` : ""}`,
      );
    },
    adoptPreview: (proposalId) =>
      http<RouteSkillProposalAdoptPreviewOut>(
        "GET",
        `/api/route-skill-proposals/${encodeURIComponent(proposalId)}/adopt-preview`,
      ),
    adopt: (proposalId) =>
      http<RouteSkillProposalAdoptOut>(
        "POST",
        `/api/route-skill-proposals/${encodeURIComponent(proposalId)}/adopt`,
      ),
    dismiss: (proposalId) =>
      http<RouteSkillProposalOut>(
        "POST",
        `/api/route-skill-proposals/${encodeURIComponent(proposalId)}/dismiss`,
      ),
  },
  tasks: {
    create: (body) => http<TaskOut>("POST", "/api/tasks", body),
    get: (runId) =>
      http<TaskOut>("GET", `/api/tasks/${encodeURIComponent(runId)}`),
    distillRouteSkills: (runId) =>
      http<TaskDistillOut>(
        "POST",
        `/api/tasks/${encodeURIComponent(runId)}/distill-route-skills`,
      ),
  },
  integrations: {
    list: () => http<IntegrationDescriptor[]>("GET", "/api/integrations"),
    get: (app) =>
      http<IntegrationDescriptor>(
        "GET",
        `/api/integrations/${encodeURIComponent(app)}`,
      ),
  },
  credentials: {
    list: () => http<CredentialListItem[]>("GET", "/api/credentials"),
    listTypes: () =>
      http<CredentialTypeSpec[]>("GET", "/api/credentials/types"),
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
  settings: {
    antibot: () => http<AntibotSettingsOut>("GET", "/api/settings/antibot"),
    runtime: () => http<RuntimeSettingsOut>("GET", "/api/settings/runtime"),
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
  expressions: {
    preview: (body) =>
      http<ExpressionPreviewResponse>("POST", "/api/expressions/preview", body),
  },
  apiKeys: {
    list: () => http<ApiKeyOut[]>("GET", "/api/v1/keys"),
    create: (body) =>
      http<ApiKeyCreated>("POST", "/api/v1/keys", body),
    remove: (keyId) =>
      http<void>("DELETE", `/api/v1/keys/${encodeURIComponent(keyId)}`),
  },
  webhooks: {
    listSubscriptions: () =>
      http<WebhookSubscriptionOut[]>("GET", "/api/internal/webhooks"),
    listSubscriptionsV1: (apiKey) =>
      http<WebhookSubscriptionOut[]>("GET", "/api/v1/webhooks", undefined, {
        apiKey,
      }),
    getSubscriptionV1: (apiKey, subscriptionId) =>
      http<WebhookSubscriptionOut>(
        "GET",
        `/api/v1/webhooks/${encodeURIComponent(subscriptionId)}`,
        undefined,
        { apiKey },
      ),
    createSubscriptionV1: (apiKey, body) =>
      http<WebhookSubscriptionOut>("POST", "/api/v1/webhooks", body, { apiKey }),
    updateSubscriptionV1: (apiKey, subscriptionId, body) =>
      http<WebhookSubscriptionOut>(
        "PATCH",
        `/api/v1/webhooks/${encodeURIComponent(subscriptionId)}`,
        body,
        { apiKey },
      ),
    removeSubscriptionV1: (apiKey, subscriptionId) =>
      http<void>(
        "DELETE",
        `/api/v1/webhooks/${encodeURIComponent(subscriptionId)}`,
        undefined,
        { apiKey },
      ),
    testSubscriptionV1: (apiKey, subscriptionId) =>
      http<WebhookTestResponse>(
        "POST",
        `/api/v1/webhooks/${encodeURIComponent(subscriptionId)}/test`,
        undefined,
        { apiKey },
      ),
    listDeliveriesV1: (apiKey, opts) => {
      const params = new URLSearchParams();
      if (opts?.subscriptionId) {
        params.set("subscription_id", opts.subscriptionId);
      }
      if (opts?.status) params.set("status", opts.status);
      if (opts?.limit) params.set("limit", String(opts.limit));
      const qs = params.toString();
      return http<WebhookDeliveryOut[]>(
        "GET",
        `/api/v1/webhooks/deliveries${qs ? `?${qs}` : ""}`,
        undefined,
        { apiKey },
      );
    },
    replayDeliveryV1: (apiKey, deliveryId) =>
      http<WebhookReplayResponse>(
        "POST",
        `/api/v1/webhooks/deliveries/${encodeURIComponent(deliveryId)}/replay`,
        undefined,
        { apiKey },
      ),
  },
  orgs: {
    listMembers: (orgId) =>
      http<OrgMemberOut[]>(
        "GET",
        `/api/orgs/${encodeURIComponent(orgId)}/members`,
      ),
    inviteMember: (orgId, body) =>
      http<OrgMemberOut>(
        "POST",
        `/api/orgs/${encodeURIComponent(orgId)}/members`,
        body,
      ),
    updateMemberRole: (orgId, userId, body) =>
      http<OrgMemberOut>(
        "PATCH",
        `/api/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`,
        body,
      ),
    removeMember: (orgId, userId) =>
      http<void>(
        "DELETE",
        `/api/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`,
      ),
    getSettings: (orgId) =>
      http<OrgSettingsOut>(
        "GET",
        `/api/orgs/${encodeURIComponent(orgId)}/settings`,
      ),
    updateSettings: (orgId, body) =>
      http<OrgSettingsOut>(
        "PATCH",
        `/api/orgs/${encodeURIComponent(orgId)}/settings`,
        body,
      ),
  },
  workers: {
    list: () => http<WorkerOut[]>("GET", "/api/workers"),
    approve: (workerId) =>
      http<WorkerOut>(
        "POST",
        `/api/workers/${encodeURIComponent(workerId)}/approve`,
      ),
    reject: (workerId) =>
      http<WorkerOut>(
        "POST",
        `/api/workers/${encodeURIComponent(workerId)}/reject`,
      ),
    revoke: (workerId) =>
      http<WorkerOut>(
        "POST",
        `/api/workers/${encodeURIComponent(workerId)}/revoke`,
      ),
  },
  admin: {
    listOrgs: async () =>
      (await http<{ items: AdminOrgOut[] }>("GET", "/api/admin/orgs")).items,
    createOrg: (body) => http<AdminOrgOut>("POST", "/api/admin/orgs", body),
    updateOrg: (orgId, body) =>
      http<AdminOrgOut>(
        "PATCH",
        `/api/admin/orgs/${encodeURIComponent(orgId)}`,
        body,
      ),
    listUsers: async () =>
      (await http<{ items: AdminUserOut[] }>("GET", "/api/admin/users")).items,
    createUser: (body) =>
      http<AdminUserOut>("POST", "/api/admin/users", body),
    updateUser: (userId, body) =>
      http<AdminUserOut>(
        "PATCH",
        `/api/admin/users/${encodeURIComponent(userId)}`,
        body,
      ),
    resetPassword: (userId, password) =>
      http<{ status: string }>(
        "POST",
        `/api/admin/users/${encodeURIComponent(userId)}/password`,
        { password },
      ),
    deleteUser: (userId) =>
      http<void>("DELETE", `/api/admin/users/${encodeURIComponent(userId)}`),
    authSettings: () =>
      http<AdminAuthSettingsOut>("GET", "/api/admin/auth/settings"),
    listDomainRules: async () =>
      (
        await http<{ items: AdminDomainRuleOut[] }>(
          "GET",
          "/api/admin/auth/domain-rules",
        )
      ).items,
    createDomainRule: (body) =>
      http<AdminDomainRuleOut>("POST", "/api/admin/auth/domain-rules", body),
    deleteDomainRule: (ruleId) =>
      http<void>(
        "DELETE",
        `/api/admin/auth/domain-rules/${encodeURIComponent(ruleId)}`,
      ),
  },
};
