export type NodeType =
  | "start"
  | "end"
  | "navigate"
  | "click"
  | "fill"
  | "extract"
  | "wait"
  | "fuzzy_action"
  | "vision_navigate"
  | "vision_act"
  | "vision_extract"
  | "desktop_open"
  | "desktop_act"
  | "desktop_navigate"
  | "desktop_extract"
  | "condition"
  | "switch"
  | "merge"
  | "set"
  | "filter"
  | "sort"
  | "limit"
  | "aggregate"
  | "split_out"
  | "remove_duplicates"
  | "rename_keys"
  | "datetime"
  | "http_request"
  | "read_file"
  | "write_file"
  | "send_email"
  | "parse_json"
  | "parse_csv"
  | "foreach"
  | "subworkflow"
  | "integration"
  | "approval";

export interface RetryPolicy {
  max_attempts: number;
  backoff_ms: number;
}

export interface WorkflowNode {
  id: string;
  type: NodeType;
  label: string;
  params: Record<string, unknown>;
  retry?: RetryPolicy | null;
  on_error?: "fail_run" | "continue" | "branch";
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  when?: "true" | "false" | null;
  case?: string | null;
  kind?: "next" | "on_error";
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

export interface Workflow {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  start_id: string;
  parameters?: WorkflowParameter[];
}

export type RunEventType =
  | "run_started"
  | "node_started"
  | "node_progress"
  | "node_completed"
  | "node_failed"
  | "node_retry"
  | "node_awaiting_approval"
  | "node_approved"
  | "node_rejected"
  | "node_self_healed"
  | "node_self_heal_failed"
  | "cache_hit"
  | "cache_miss"
  | "branch_pruned"
  | "node_skipped"
  | "merge_waiting"
  | "run_completed"
  | "run_completed_with_errors"
  | "run_failed"
  | "run_aborted"
  | "run_rejected";

export interface ItemsPreview {
  json?: Record<string, unknown>;
  binary?: Record<string, Record<string, unknown>>;
}

export interface RunEvent {
  event: RunEventType;
  node_id?: string;
  ts: string;
  message?: string;
  output?: unknown;
  error?: string;
  attempt?: number;
  error_kind?: string;
  next_attempt_at?: string;
  failed_node_count?: number;
  failed_node_ids?: string[];
  prompt?: string;
  decision?: string;
  inputs?: unknown;
  original_selector?: string;
  new_selector?: string | null;
  confidence?: number;
  mode?: string;
  reason?: string;
  url_pattern?: string;
  selector?: string;
  cache_entry_id?: string;
  post_heal_error?: string | null;
  items_count?: number;
  items_preview?: ItemsPreview;
  edge_id?: string;
  arrived?: number;
  expected?: number;
  payload?: Record<string, unknown>;
}

export type NodeStatus =
  | "idle"
  | "running"
  | "success"
  | "error"
  | "skipped"
  | "waiting";

export interface NodeRuntimeState {
  status: NodeStatus;
  message?: string;
  output?: unknown;
  error?: string;
  mergeWaiting?: { arrived: number; expected: number };
}
