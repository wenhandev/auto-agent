import { create } from "zustand";
import type {
  NodeRuntimeState,
  RunEvent,
  Workflow,
} from "./types";
import type {
  PendingApproval,
  RunStatus,
  WSEvent,
  WorkflowVersionOut,
} from "./types-platform";

export type PlatformRunStatus = RunStatus | "idle";

interface PlatformState {
  currentWorkflowId: string | null;
  currentWorkflow: Workflow | null;
  currentVersion: WorkflowVersionOut | null;
  currentRunId: string | null;
  currentRunStatus: PlatformRunStatus;
  pendingApproval: PendingApproval | null;
  activeWS: WebSocket | null;
  versions: WorkflowVersionOut[];
  isWorkflowDirty: boolean;
  nodeStates: Record<string, NodeRuntimeState>;
  events: WSEvent[];

  setCurrentWorkflow(
    workflowId: string,
    workflow: Workflow,
    version: WorkflowVersionOut | null,
  ): void;
  /** Sync workflow definition without clearing active run state. */
  syncWorkflowDefinition(
    workflowId: string,
    workflow: Workflow,
    version: WorkflowVersionOut | null,
  ): void;
  clearCurrentWorkflow(): void;
  setVersions(versions: WorkflowVersionOut[]): void;
  markWorkflowDirty(): void;
  clearWorkflowDirty(): void;
  setCurrentRun(runId: string | null, status: PlatformRunStatus): void;
  setRunStatus(status: PlatformRunStatus): void;
  setPendingApproval(approval: PendingApproval | null): void;
  setActiveWS(ws: WebSocket | null): void;
  resetRunState(): void;
  applyEvent(ev: WSEvent | RunEvent): void;
}

function freshNodeStates(wf: Workflow | null): Record<string, NodeRuntimeState> {
  const out: Record<string, NodeRuntimeState> = {};
  if (!wf) return out;
  for (const node of wf.nodes) {
    out[node.id] = { status: "idle" };
  }
  return out;
}

export const usePlatformStore = create<PlatformState>((set, get) => ({
  currentWorkflowId: null,
  currentWorkflow: null,
  currentVersion: null,
  currentRunId: null,
  currentRunStatus: "idle",
  pendingApproval: null,
  activeWS: null,
  versions: [],
  isWorkflowDirty: false,
  nodeStates: {},
  events: [],

  setCurrentWorkflow(workflowId, workflow, version) {
    set({
      currentWorkflowId: workflowId,
      currentWorkflow: workflow,
      currentVersion: version,
      isWorkflowDirty: false,
      nodeStates: freshNodeStates(workflow),
      events: [],
      currentRunId: null,
      currentRunStatus: "idle",
      pendingApproval: null,
    });
  },

  syncWorkflowDefinition(workflowId, workflow, version) {
    set({
      currentWorkflowId: workflowId,
      currentWorkflow: workflow,
      currentVersion: version,
      isWorkflowDirty: false,
    });
  },

  clearCurrentWorkflow() {
    set({
      currentWorkflowId: null,
      currentWorkflow: null,
      currentVersion: null,
      versions: [],
      isWorkflowDirty: false,
      nodeStates: {},
      events: [],
      currentRunId: null,
      currentRunStatus: "idle",
      pendingApproval: null,
      activeWS: null,
    });
  },

  setVersions(versions) {
    set({ versions });
  },

  markWorkflowDirty() {
    set({ isWorkflowDirty: true });
  },

  clearWorkflowDirty() {
    set({ isWorkflowDirty: false });
  },

  setCurrentRun(runId, status) {
    set({ currentRunId: runId, currentRunStatus: status, pendingApproval: null });
  },

  setRunStatus(status) {
    set({ currentRunStatus: status });
  },

  setPendingApproval(approval) {
    set({ pendingApproval: approval });
  },

  setActiveWS(ws) {
    set({ activeWS: ws });
  },

  resetRunState() {
    const wf = get().currentWorkflow;
    set({
      nodeStates: freshNodeStates(wf),
      events: [],
      currentRunId: null,
      currentRunStatus: "idle",
      pendingApproval: null,
    });
  },

  applyEvent(ev) {
    const prevStates = get().nodeStates;
    const prevEvents = get().events;
    const wsEv = ev as WSEvent;
    const next: Partial<PlatformState> = {
      events: [...prevEvents, wsEv],
    };

    switch (wsEv.event) {
      case "run_queued": {
        next.currentRunStatus = "queued";
        break;
      }
      case "run_started": {
        next.currentRunStatus = "running";
        next.nodeStates = freshNodeStates(get().currentWorkflow);
        break;
      }
      case "node_started": {
        if (wsEv.node_id) {
          const prev = prevStates[wsEv.node_id] ?? { status: "idle" };
          next.nodeStates = {
            ...prevStates,
            [wsEv.node_id]: {
              ...prev,
              status: "running",
              message: undefined,
              output: undefined,
              error: undefined,
            },
          };
        }
        break;
      }
      case "node_progress": {
        if (wsEv.node_id) {
          const prev = prevStates[wsEv.node_id] ?? { status: "running" };
          next.nodeStates = {
            ...prevStates,
            [wsEv.node_id]: {
              ...prev,
              status: "running",
              message: wsEv.message ?? undefined,
            },
          };
        }
        break;
      }
      case "node_completed": {
        if (wsEv.node_id) {
          const prev = prevStates[wsEv.node_id] ?? { status: "idle" };
          next.nodeStates = {
            ...prevStates,
            [wsEv.node_id]: {
              ...prev,
              status: "success",
              message: undefined,
              output: wsEv.output,
            },
          };
        }
        break;
      }
      case "node_failed": {
        if (wsEv.node_id) {
          const prev = prevStates[wsEv.node_id] ?? { status: "idle" };
          next.nodeStates = {
            ...prevStates,
            [wsEv.node_id]: {
              ...prev,
              status: "error",
              message: wsEv.error ?? wsEv.message ?? undefined,
              error: wsEv.error ?? undefined,
            },
          };
        }
        break;
      }
      case "node_awaiting_approval": {
        if (wsEv.node_id && wsEv.prompt) {
          next.pendingApproval = {
            node_id: wsEv.node_id,
            prompt: wsEv.prompt,
            inputs_schema: wsEv.inputs_schema ?? [],
            requested_at: wsEv.ts,
            captcha_kind: wsEv.captcha_kind ?? null,
          };
        }
        break;
      }
      case "node_approved":
      case "node_rejected": {
        next.pendingApproval = null;
        break;
      }
      case "run_completed": {
        next.currentRunStatus = "completed";
        break;
      }
      case "run_completed_with_errors": {
        next.currentRunStatus = "completed_with_errors";
        break;
      }
      case "run_rejected": {
        next.currentRunStatus = "rejected";
        next.pendingApproval = null;
        break;
      }
      case "run_failed": {
        next.currentRunStatus = "failed";
        next.pendingApproval = null;
        break;
      }
      case "run_aborted": {
        next.currentRunStatus = "aborted";
        next.pendingApproval = null;
        break;
      }
    }

    set(next as PlatformState);
  },
}));
