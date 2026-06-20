import type { Workflow, WorkflowNode, WorkflowEdge } from "./types";

export type { Workflow, WorkflowNode, WorkflowEdge };

export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "aborted"
  | "rejected";

export type ChatRole = "user" | "assistant" | "system";

export type AuthoredBy = "planner" | "editor" | "manual";

export interface WorkflowCreate {
  name: string;
  description?: string | null;
}

export interface WorkflowUpdate {
  name?: string | null;
  description?: string | null;
}

export interface WorkflowVersionCreate {
  workflow: Workflow;
  authored_by?: AuthoredBy;
}

export interface WorkflowVersionOut {
  id: string;
  workflow_id: string;
  version_index: number;
  authored_by: AuthoredBy;
  workflow: Workflow;
  created_at: string;
}

export interface WorkflowOut {
  id: string;
  name: string;
  description: string | null;
  current_version: WorkflowVersionOut | null;
  chat_session_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowListItem {
  id: string;
  name: string;
  description: string | null;
  current_version_index: number | null;
  last_run_status: RunStatus | null;
  updated_at: string;
}

export interface LastOutputShapesResponse {
  run_id: string | null;
  started_at: string | null;
  shapes: Record<string, unknown>;
}

export type PatchOp =
  | { op: "add_node"; node: WorkflowNode }
  | { op: "remove_node"; id: string }
  | { op: "update_node"; id: string; patch: Record<string, unknown> }
  | { op: "add_edge"; edge: WorkflowEdge }
  | { op: "remove_edge"; id: string }
  | { op: "set_start"; id: string };

export interface ChatTurnRequest {
  message: string;
}

export interface ChatMessageOut {
  id: string;
  session_id: string;
  role: ChatRole;
  content: string;
  workflow_version_id: string | null;
  created_at: string;
}

export interface ChatTurnResponse {
  assistant_message: ChatMessageOut;
  patch: PatchOp[] | null;
  new_version: WorkflowVersionOut | null;
}

export type ParameterType = "string" | "number" | "boolean" | "secret" | "json" | "file";

export interface WorkflowParameter {
  name: string;
  type: ParameterType;
  label?: string | null;
  required?: boolean;
  default?: unknown;
  description?: string | null;
}

export interface RunCreate {
  browser_profile_id?: string | null;
  browser_session_id?: string | null;
  parameters?: Record<string, unknown> | null;
  totp_identifier?: string | null;
  record_video?: boolean | null;
  execution_mode?: "cloud" | "worker";
  worker_id?: string | null;
  worker_pool?: string | null;
}

export interface StagingFileOut {
  file_id: string;
  filename: string;
  content_type: string;
  bytes: number;
}

export interface PendingApproval {
  node_id: string;
  prompt: string;
  inputs_schema: ApprovalInputSpec[];
  requested_at: string;
  captcha_kind?: string | null;
}

export interface ApprovalInputSpec {
  name: string;
  type: "string" | "number" | "boolean";
  required?: boolean;
  default?: unknown;
  label?: string | null;
}

export interface ApprovalDecisionRequest {
  decision: "approve" | "reject";
  inputs?: Record<string, unknown>;
}

export interface ApprovalDecisionResponse {
  node_id: string;
  decision: "approve" | "reject";
  inputs: Record<string, unknown>;
  resolved_at: string;
}

export interface PendingApprovalOut {
  id: string;
  run_id: string;
  node_id: string;
  seq: number;
  prompt: string;
  inputs_schema: ApprovalInputSpec[];
  requested_at: string;
  captcha_kind?: string | null;
}

export type ArtifactKind =
  | "screenshot"
  | "recording"
  | "trace"
  | "llm_trace"
  | "download"
  | "har";

export interface RunArtifactOut {
  id: string;
  run_id: string;
  kind: ArtifactKind;
  content_type: string;
  bytes: number;
  node_id?: string | null;
  step_index?: number | null;
  filename?: string | null;
  note?: string | null;
  deleted_at?: string | null;
  created_at: string;
  expired: boolean;
}

export interface ViewportSpec {
  width: number;
  height: number;
}

export interface BrowserProfileCreate {
  name: string;
  user_agent?: string | null;
  viewport?: ViewportSpec | null;
  persist_cookies?: boolean;
  persist_local_storage?: boolean;
}

export interface BrowserProfileUpdate {
  name?: string | null;
  user_agent?: string | null;
  viewport?: ViewportSpec | null;
  persist_cookies?: boolean | null;
  persist_local_storage?: boolean | null;
}

export interface BrowserProfileOut {
  id: string;
  name: string;
  user_agent?: string | null;
  viewport?: ViewportSpec | null;
  persist_cookies: boolean;
  persist_local_storage: boolean;
  has_storage_state: boolean;
  created_at: string;
  updated_at: string;
  last_used_at?: string | null;
}

export type RecordingStatus = "active" | "stopped" | "synthesized";

export interface RecordingCreate {
  name?: string | null;
  browser_profile_id?: string | null;
  start_url?: string | null;
  acquire_browser?: boolean;
}

export interface RecordingEvent {
  type: string;
  url?: string | null;
  selector?: string | null;
  description?: string | null;
  name?: string | null;
  value?: string | null;
  ts?: string | null;
  [key: string]: unknown;
}

export interface RecordingOut {
  id: string;
  status: RecordingStatus;
  name?: string | null;
  browser_profile_id?: string | null;
  start_url?: string | null;
  event_count: number;
  events: RecordingEvent[];
  generated_workflow_id?: string | null;
  generated_workflow?: Record<string, unknown> | null;
  created_at: string;
  started_at: string;
  stopped_at?: string | null;
}

export interface RecordingGenerateOut {
  recording_id: string;
  workflow_id: string;
  chat_session_id: string;
  workflow: Record<string, unknown>;
}

export interface ApiKeyOut {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at?: string | null;
}

export interface ApiKeyCreate {
  name: string;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  prefix: string;
  key: string;
  created_at: string;
}

export type WebhookEventName =
  | "run_completed"
  | "run_failed"
  | "run_rejected"
  | "run_aborted"
  | "approval_requested";

export type WebhookDeliveryStatus =
  | "pending"
  | "delivered"
  | "failed"
  | "exhausted";

export interface WebhookSubscriptionOut {
  id: string;
  url: string;
  events: WebhookEventName[];
  enabled: boolean;
  workflow_id?: string | null;
  secret_masked: string;
  created_at: string;
  updated_at: string;
}

export interface WebhookSubscriptionCreate {
  url: string;
  events: WebhookEventName[];
  secret?: string | null;
  enabled?: boolean;
  workflow_id?: string | null;
}

export interface WebhookSubscriptionUpdate {
  url?: string | null;
  events?: WebhookEventName[] | null;
  secret?: string | null;
  enabled?: boolean | null;
  workflow_id?: string | null;
}

export interface WebhookDeliveryOut {
  id: string;
  subscription_id: string;
  event: string;
  attempt: number;
  status: WebhookDeliveryStatus;
  response_code: number | null;
  next_attempt_at: string | null;
  signature: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WebhookTestResponse {
  delivery_id: string;
  status: "queued";
}

export interface WebhookReplayResponse {
  delivery_id: string;
  status: "pending";
}

export interface OrgMemberOut {
  user_id: string;
  email: string;
  name: string | null;
  role: string;
  created_at: string;
}

export interface OrgMemberInvite {
  email: string;
  role?: string;
  name?: string | null;
  password?: string | null;
}

export interface OrgMemberRoleUpdate {
  role: string;
}

export interface IntegrationFieldSpec {
  name: string;
  label?: string;
  kind: "string" | "number" | "boolean" | "options";
  required?: boolean;
  default?: unknown;
  options?: { value: string; label?: string }[];
}

export interface IntegrationOperationSpec {
  name: string;
  label?: string;
  fields: IntegrationFieldSpec[];
}

export interface IntegrationResourceSpec {
  name: string;
  label?: string;
  operations: IntegrationOperationSpec[];
}

export interface IntegrationDescriptor {
  app: string;
  version?: string;
  credentials?: string[];
  resources: IntegrationResourceSpec[];
  triggers?: IntegrationTriggerSpec[];
}

export interface IntegrationTriggerSpec {
  name: string;
  label?: string;
  kind: "poll" | "webhook";
  resource?: string;
  list_operation?: string;
  subscribe_operation?: string;
  dedup_path?: string;
  item_path?: string;
}

export interface ExpressionPreviewRequest {
  expression: string;
  workflow_id?: string;
  context?: Record<string, unknown>;
}

export interface ExpressionPreviewResponse {
  ok: boolean;
  type: string | null;
  value: unknown;
  error: string | null;
}

export interface NodeRetryPayload {
  attempt: number;
  error: string;
  error_kind: string;
  next_attempt_at: string;
}

export interface RunCompletedWithErrorsPayload {
  failed_node_count: number;
  failed_node_ids: string[];
}

export interface RunOut {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  status: RunStatus;
  mode?: "graph" | "autonomous";
  objective?: string | null;
  task_result?: TaskResultOut | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  parameters?: Record<string, unknown> | null;
  artifact_counts?: Record<string, number>;
  browser_profile_id?: string | null;
  browser_session_id?: string | null;
  browser_provider_id?: string | null;
  browser_provider_metadata?: Record<string, unknown>;
  agent_loop_metrics?: Record<string, unknown> | null;
  pending_approval?: PendingApproval | null;
  total_input_tokens?: number;
  total_output_tokens?: number;
  total_llm_calls?: number;
  total_vision_calls?: number;
  estimated_cost_usd?: number | null;
  cost_note?: string | null;
  execution_mode?: "cloud" | "worker";
  worker_id?: string | null;
  worker_pool?: string | null;
  worker_name?: string | null;
  queue_reason?: string | null;
}

export type WorkerEnvironmentStatus =
  | "ready"
  | "degraded"
  | "not_ready"
  | "unknown";

export interface WorkerEnvironmentCheck {
  id: string;
  status: "pass" | "warn" | "fail";
  message?: string | null;
}

export type WorkerApprovalStatus = "pending" | "approved" | "rejected";
export type DesktopClientPolicy = "disabled" | "approval_required" | "open";

export interface WorkerOut {
  id: string;
  machine_id: string;
  display_name?: string | null;
  hostname: string;
  user_id: string;
  user_email?: string | null;
  org_id: string;
  status: "online" | "offline";
  tags: string[];
  max_concurrent_runs: number;
  active_runs: number;
  agent_version?: string | null;
  environment_status: WorkerEnvironmentStatus;
  environment_checks: WorkerEnvironmentCheck[];
  capabilities: Record<string, unknown>;
  last_seen_at?: string | null;
  created_at: string;
  revoked_at?: string | null;
  approval_status: WorkerApprovalStatus;
  approved_at?: string | null;
  approved_by_user_id?: string | null;
  desktop_client_policy?: DesktopClientPolicy | null;
}

export interface OrgSettingsOut {
  org_id: string;
  desktop_client_policy: DesktopClientPolicy;
}

export interface OrgSettingsUpdate {
  desktop_client_policy: DesktopClientPolicy;
}

export interface RunEventOut {
  id: number;
  run_id: string;
  seq: number;
  event_type: string;
  node_id: string | null;
  ts: string;
  payload: Record<string, unknown>;
}

export interface RunListItem {
  id: string;
  workflow_id: string;
  workflow_name: string;
  workflow_version_id: string;
  version_index: number;
  status: RunStatus;
  mode?: "graph" | "autonomous";
  objective?: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error_summary: string | null;
  pending_approval?: PendingApproval | null;
  queue_position?: number | null;
  total_input_tokens?: number;
  total_output_tokens?: number;
  estimated_cost_usd?: number | null;
  cost_note?: string | null;
  execution_mode?: "cloud" | "worker";
  worker_id?: string | null;
  worker_name?: string | null;
  queue_reason?: string | null;
}

export interface RunReplayResponse {
  run: RunOut;
  workflow_version: WorkflowVersionOut;
  events: RunEventOut[];
}

export interface CredentialCreate {
  name: string;
  description?: string | null;
  type?: string;
  fields: Record<string, string>;
}

export interface CredentialUpdate {
  name?: string | null;
  description?: string | null;
  type?: string | null;
  fields?: Record<string, string> | null;
}

export interface CredentialFieldMasked {
  name: string;
  masked_value: string;
}

export interface CredentialOut {
  id: string;
  name: string;
  type: string;
  description: string | null;
  fields: CredentialFieldMasked[];
  created_at: string;
  updated_at: string;
}

export interface CredentialListItem {
  id: string;
  name: string;
  type: string;
  description: string | null;
  field_names: string[];
  updated_at: string;
  usage_count?: number;
}

export interface CredentialTypeFieldSpec {
  name: string;
  label: string;
  kind: string;
  required?: boolean;
  default?: unknown;
}

export interface CredentialTypeAuthSpec {
  strategy: string;
  connect_app?: string | null;
}

export interface CredentialTypeSpec {
  type: string;
  label: string;
  fields: CredentialTypeFieldSpec[];
  auth: CredentialTypeAuthSpec;
}

export interface WorkflowCredentialLinkRequest {
  credential_id: string;
}

export interface LlmConfigUpsert {
  provider: string;
  model: string;
  api_key: string;
  base_url?: string | null;
  self_healing_enabled?: boolean | null;
  self_healing_vision_threshold?: number | null;
}

export interface LlmConfigOut {
  id: string;
  provider: string;
  model: string;
  api_key_masked: string;
  base_url: string | null;
  is_active: boolean;
  self_healing_enabled: boolean;
  self_healing_vision_threshold: number;
  created_at: string;
  updated_at: string;
}

export interface LlmEffectiveOut {
  source: "db" | "env";
  provider: string;
  model: string;
  api_key_masked: string;
  base_url: string | null;
}

export interface AntibotSettingsOut {
  source: "env";
  editable: false;
  captcha_detection_enabled: boolean;
  captcha_builtin_heuristics_enabled: boolean;
  captcha_solver: "manual" | "external";
  captcha_external_solver_url_masked: string | null;
  captcha_external_solver_key_configured: boolean;
  antibot_stealth: boolean;
  antibot_user_agent: string | null;
  antibot_locale: string | null;
  antibot_timezone_id: string | null;
  antibot_viewport_width: number | null;
  antibot_viewport_height: number | null;
  default_proxy_id: string | null;
  proxy_configured: boolean;
  proxy_url_masked: string | null;
  proxy_username_configured: boolean;
  proxy_password_configured: boolean;
}

export interface WSStartFrame {
  type: "start";
  run_id?: string | null;
  workflow?: Workflow | null;
}

export interface WSAbortFrame {
  type: "abort";
  run_id?: string | null;
}

export type WSClientFrame = WSStartFrame | WSAbortFrame;

export interface WSEvent {
  event: string;
  run_id?: string | null;
  node_id?: string | null;
  seq?: number | null;
  ts: string;
  message?: string | null;
  output?: unknown;
  error?: string | null;
  prompt?: string | null;
  inputs_schema?: ApprovalInputSpec[] | null;
  captcha_kind?: string | null;
}

export interface SelfHealCostHint {
  input_tokens?: number | null;
  output_tokens?: number | null;
  vision_calls: number;
}

export interface SelfHealConfig {
  enabled: boolean;
  vision_threshold: number;
}

export interface SelfHealEvent extends WSEvent {
  event: "node_self_healed";
  mode: "dom" | "vision";
  old_selector: string;
  new_selector: string | null;
  confidence: number;
  cost_hint: SelfHealCostHint;
  post_heal_error?: string | null;
}

// === triggers-and-scheduling additions ===

export type TriggerType = "cron" | "webhook" | "manual" | "poll" | "app";
export type TriggerAuthMode = "query_secret" | "hmac";
export type PollMode = "per_record" | "batched";
export type OnFirstPoll = "fire_all" | "fire_none" | "fire_latest";

export interface TriggerOut {
  id: string;
  workflow_id: string;
  type: TriggerType;
  schedule_or_path: string;
  enabled: boolean;
  auth_mode: TriggerAuthMode;
  last_fired_at: string | null;
  created_at: string;
  updated_at: string;
  webhook_url: string | null;
  secret_masked: string | null;
  secret_full: string | null;
  poll_app?: string | null;
  poll_resource?: string | null;
  poll_operation?: string | null;
  poll_credential?: string | null;
  poll_dedup_path?: string | null;
  poll_mode?: PollMode;
  on_first_poll?: OnFirstPoll;
  min_poll_interval_s?: number;
  last_polled_at?: string | null;
  app_name?: string | null;
  app_trigger?: string | null;
  app_credential?: string | null;
  subscription_id?: string | null;
  app_callback_url?: string | null;
  subscription_status?: string | null;
}

export interface TriggerCreate {
  type: TriggerType;
  schedule_or_path?: string | null;
  enabled?: boolean;
  poll_app?: string | null;
  poll_resource?: string | null;
  poll_operation?: string | null;
  poll_credential?: string | null;
  poll_dedup_path?: string | null;
  poll_mode?: PollMode;
  on_first_poll?: OnFirstPoll;
  min_poll_interval_s?: number;
  app_name?: string | null;
  app_trigger?: string | null;
  app_credential?: string | null;
}

export interface TriggerUpdate {
  enabled?: boolean | null;
  schedule_or_path?: string | null;
  regenerate_secret?: boolean;
}

export interface WebhookFireResponse {
  run_id: string;
  status: "queued";
}

export interface OrgMembershipOut {
  org_id: string;
  org_name: string;
  role: string;
}

export interface MeResponse {
  id: string;
  email: string;
  name: string | null;
  current_org_id: string;
  role: string | null;
  is_platform_admin: boolean;
  memberships: OrgMembershipOut[];
}

export interface AdminOrgOut {
  id: string;
  name: string;
  desktop_client_policy: DesktopClientPolicy;
  created_at: string;
}

export interface AdminUserOut {
  id: string;
  email: string;
  name: string | null;
  is_platform_admin: boolean;
  disabled_at: string | null;
  created_at: string;
  memberships: OrgMembershipOut[];
}

export interface AdminOrgCreate {
  name: string;
  desktop_client_policy?: DesktopClientPolicy;
}

export interface AdminOrgUpdate {
  name?: string;
  desktop_client_policy?: DesktopClientPolicy;
}

export interface AdminUserCreate {
  email: string;
  name?: string | null;
  password?: string | null;
  org_id: string;
  role?: string;
  is_platform_admin?: boolean;
}

export interface AdminUserUpdate {
  name?: string | null;
  is_platform_admin?: boolean;
  disabled?: boolean;
}

export interface AdminDomainRuleCreate {
  domain: string;
  org_id: string;
  default_role?: string;
}

export interface AdminAuthSettingsOut {
  providers: { google: boolean };
  signup_policy: string;
  password_login_enabled: boolean;
}

export interface AdminDomainRuleOut {
  id: string;
  domain: string;
  org_id: string;
  default_role: string;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: MeResponse;
}

export type BrowserSessionStatus = "live" | "idle" | "closed" | "expired";

export interface BrowserSessionCreate {
  profile_id?: string | null;
  provider_id?: string | null;
  provider_config?: Record<string, unknown> | null;
}

export interface BrowserSessionMemoryEntry {
  objective?: string;
  success?: boolean;
  summary?: string;
  final_url?: string | null;
  extracted_summary?: unknown[];
  created_at?: string;
}

export interface BrowserSessionOut {
  id: string;
  profile_id: string | null;
  status: BrowserSessionStatus;
  started_at: string;
  expires_at: string;
  last_activity_at: string;
  seconds_until_expiry: number | null;
  provider_id?: string;
  provider_metadata?: Record<string, unknown>;
}

export interface PickerEnableOut {
  picker_token: string;
  mode: string;
}

export interface SelectorCandidateOut {
  selector: string;
  strategy: string;
  confidence: number;
  match_count: number;
}

export interface PickElementOut {
  candidates: SelectorCandidateOut[];
  element_summary?: {
    tag?: string | null;
    role?: string | null;
    name?: string | null;
    text?: string | null;
  } | null;
  viewport?: { width: number; height: number } | null;
  error?: string | null;
}

export interface TestSelectorOut {
  match_count: number;
  preview: {
    tag?: string | null;
    text?: string | null;
    role?: string | null;
    visible?: boolean;
  };
}

export interface RouteSkillOut {
  id: string;
  scope: string;
  url_pattern: string;
  prompt: string;
  allowed_tools: string[];
  priority: number;
  enabled: boolean;
}

export interface TaskCreate {
  objective: string;
  start_url?: string | null;
  max_steps?: number;
  max_seconds?: number;
  success_criteria?: string | null;
  allowed_domains?: string[] | null;
  data_schema?: Record<string, unknown> | null;
  require_confirmation?: boolean;
  allowed_tools?: string[] | null;
  synthesize_workflow?: boolean;
}

export interface TaskResultOut {
  success: boolean;
  summary: string;
  user_message?: string | null;
  data?: unknown;
  items: unknown[];
  reason?: string | null;
  steps_taken: number;
  synthesized_workflow_id?: string | null;
}

export interface TaskOut {
  id: string;
  mode: "autonomous";
  status: RunStatus;
  objective: string;
  start_url: string | null;
  max_steps: number;
  max_seconds: number;
  success_criteria: string | null;
  allowed_domains: string[] | null;
  data_schema: Record<string, unknown> | null;
  require_confirmation: boolean;
  allowed_tools: string[] | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  result: TaskResultOut | null;
}
