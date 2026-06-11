import type { Workflow, WorkflowNode, WorkflowEdge } from "./types";

export type { Workflow, WorkflowNode, WorkflowEdge };

export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "aborted";

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

export interface RunCreate {}

export interface RunOut {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  status: RunStatus;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
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
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error_summary: string | null;
}

export interface RunReplayResponse {
  run: RunOut;
  workflow_version: WorkflowVersionOut;
  events: RunEventOut[];
}

export interface CredentialCreate {
  name: string;
  description?: string | null;
  fields: Record<string, string>;
}

export interface CredentialUpdate {
  name?: string | null;
  description?: string | null;
  fields?: Record<string, string> | null;
}

export interface CredentialFieldMasked {
  name: string;
  masked_value: string;
}

export interface CredentialOut {
  id: string;
  name: string;
  description: string | null;
  fields: CredentialFieldMasked[];
  created_at: string;
  updated_at: string;
}

export interface CredentialListItem {
  id: string;
  name: string;
  description: string | null;
  field_names: string[];
  updated_at: string;
  usage_count?: number;
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

export type TriggerType = "cron" | "webhook" | "manual";
export type TriggerAuthMode = "query_secret" | "hmac";

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
}

export interface TriggerCreate {
  type: TriggerType;
  schedule_or_path?: string | null;
  enabled?: boolean;
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
