export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "aborted"
  | "rejected";

export const TERMINAL_RUN_STATUSES: readonly RunStatus[] = [
  "completed",
  "completed_with_errors",
  "failed",
  "aborted",
  "rejected",
] as const;

export interface RunTaskRequest {
  prompt: string;
  url?: string;
  data_schema?: Record<string, unknown>;
  browser_session_id?: string;
  browser_profile_id?: string;
  totp_identifier?: string;
  max_steps?: number;
  persist?: boolean;
}

export interface RunTaskResponse {
  run_id: string;
  status: RunStatus;
}

export interface RunCreate {
  browser_profile_id?: string;
  browser_session_id?: string;
  parameters?: Record<string, unknown>;
  totp_identifier?: string;
}

export interface PendingApproval {
  node_id: string;
  prompt: string;
  inputs_schema: Record<string, unknown>[];
  requested_at: string;
}

export interface RunOut {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  status: RunStatus;
  mode?: "graph" | "autonomous";
  queued_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  source?: string;
  trigger_id?: string | null;
  trigger_context?: Record<string, unknown> | null;
  parameters?: Record<string, unknown> | null;
  artifact_counts?: Record<string, number>;
  browser_profile_id?: string | null;
  browser_session_id?: string | null;
  totp_identifier?: string | null;
  pending_approval?: PendingApproval | null;
  queue_position?: number | null;
  total_input_tokens?: number;
  total_output_tokens?: number;
  total_llm_calls?: number;
  total_vision_calls?: number;
  estimated_cost_usd?: number | null;
  cost_note?: string | null;
  usage_summary?: Record<string, unknown> | null;
  node_costs?: Record<string, unknown>[];
}

export interface RunEventOut {
  id: number;
  run_id: string;
  seq: number;
  event_type: string;
  node_id?: string | null;
  ts: string;
  payload: Record<string, unknown>;
}

export interface WorkflowVersionOut {
  id: string;
  workflow_id: string;
  version_index: number;
  authored_by: "planner" | "editor" | "manual";
  workflow: Record<string, unknown>;
  created_at: string;
}

export interface RunReplayResponse {
  run: RunOut;
  workflow_version: WorkflowVersionOut;
  events: RunEventOut[];
}

export interface RunListItem {
  id: string;
  workflow_id: string;
  workflow_name: string;
  workflow_version_id: string;
  version_index: number;
  status: RunStatus;
  queued_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  error_summary?: string | null;
  pending_approval?: PendingApproval | null;
  queue_position?: number | null;
  total_input_tokens?: number;
  total_output_tokens?: number;
  total_llm_calls?: number;
  total_vision_calls?: number;
  estimated_cost_usd?: number | null;
  cost_note?: string | null;
}

export interface RunListPage {
  items: RunListItem[];
  next_cursor?: string | null;
}

export interface WorkflowListItem {
  id: string;
  name: string;
  description?: string | null;
  current_version_index?: number | null;
  last_run_status?: RunStatus | null;
  updated_at: string;
}

export type RunHandle = string | RunOut | RunTaskResponse | RunReplayResponse;

export function runIdFromHandle(run: RunHandle): string {
  if (typeof run === "string") {
    return run;
  }
  if ("run_id" in run) {
    return run.run_id;
  }
  if ("run" in run) {
    return run.run.id;
  }
  return run.id;
}

export function isTerminalStatus(status: RunStatus): boolean {
  return (TERMINAL_RUN_STATUSES as readonly string[]).includes(status);
}
