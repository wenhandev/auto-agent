export type WorkerApprovalStatus = "pending" | "approved" | "rejected";

export interface WorkerLoginResponse {
  worker_session_token: string;
  worker_id: string;
  org_id: string;
  expires_at: string;
  approval_status: WorkerApprovalStatus;
  desktop_client_policy: "disabled" | "approval_required" | "open";
}

export interface WorkerMeResponse {
  id: string;
  machine_id: string;
  display_name: string | null;
  hostname: string;
  approval_status: WorkerApprovalStatus;
  tags: string[];
  status: "online" | "offline";
  environment_status: "ready" | "degraded" | "not_ready" | "unknown";
}

export interface SidecarStatus {
  approval_status: WorkerApprovalStatus | "unknown";
  connected: boolean;
  logged_in: boolean;
  cloud_url: string | null;
  worker_id: string | null;
  agent_version: string;
  preflight: {
    environment_status: string;
    checks: Array<{ id: string; status: string; message: string }>;
  };
}

export interface DesktopSession {
  cloudUrl: string;
  workerSessionToken: string;
  webSessionToken: string;
  workerId: string;
  orgId: string;
  approvalStatus: WorkerApprovalStatus;
  machineId: string;
  displayName: string;
  tags: string[];
}

export interface LocalRunMeta {
  id: string;
  workflow_id?: string | null;
  status: string;
  started_at: string;
  finished_at?: string | null;
}

export interface CloudWorkflowListItem {
  id: string;
  name: string;
  description?: string | null;
  current_version_index?: number | null;
  updated_at: string;
}

export interface LlmSettings {
  llm_provider?: string;
  openai_api_key?: string;
  openai_model?: string;
  openai_base_url?: string | null;
  google_api_key?: string;
  google_model?: string;
  google_base_url?: string | null;
  gemini_provider?: string;
  gcp_project?: string;
  gcp_location?: string;
}

export interface WorkflowDraftMeta {
  local_id: string;
  workflow_id?: string | null;
  name: string;
  cloud_version_id?: string | null;
  published_at?: string | null;
  publish_queued?: boolean;
  updated_at: string;
  created_at: string;
}
