export type NodeType =
  | "start"
  | "end"
  | "navigate"
  | "click"
  | "fill"
  | "extract"
  | "wait"
  | "fuzzy_action"
  | "condition";

export interface WorkflowNode {
  id: string;
  type: NodeType;
  label: string;
  params: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  when?: "true" | "false" | null;
}

export interface Workflow {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  start_id: string;
}

export type RunEventType =
  | "run_started"
  | "node_started"
  | "node_progress"
  | "node_completed"
  | "node_failed"
  | "run_completed"
  | "run_failed";

export interface RunEvent {
  event: RunEventType;
  node_id?: string;
  ts: string;
  message?: string;
  output?: unknown;
  error?: string;
}

export type NodeStatus = "idle" | "running" | "success" | "error";

export interface NodeRuntimeState {
  status: NodeStatus;
  message?: string;
  output?: unknown;
  error?: string;
}
