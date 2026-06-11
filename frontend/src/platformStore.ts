import { create } from "zustand";
import type {
  NodeRuntimeState,
  RunEvent,
  Workflow,
} from "./types";
import type {
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
  activeWS: WebSocket | null;
  versions: WorkflowVersionOut[];
  nodeStates: Record<string, NodeRuntimeState>;
  events: WSEvent[];

  setCurrentWorkflow(
    workflowId: string,
    workflow: Workflow,
    version: WorkflowVersionOut | null,
  ): void;
  clearCurrentWorkflow(): void;
  setVersions(versions: WorkflowVersionOut[]): void;
  setCurrentRun(runId: string | null, status: PlatformRunStatus): void;
  setRunStatus(status: PlatformRunStatus): void;
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
  activeWS: null,
  versions: [],
  nodeStates: {},
  events: [],

  setCurrentWorkflow(workflowId, workflow, version) {
    set({
      currentWorkflowId: workflowId,
      currentWorkflow: workflow,
      currentVersion: version,
      nodeStates: freshNodeStates(workflow),
      events: [],
      currentRunId: null,
      currentRunStatus: "idle",
    });
  },

  clearCurrentWorkflow() {
    set({
      currentWorkflowId: null,
      currentWorkflow: null,
      currentVersion: null,
      versions: [],
      nodeStates: {},
      events: [],
      currentRunId: null,
      currentRunStatus: "idle",
      activeWS: null,
    });
  },

  setVersions(versions) {
    set({ versions });
  },

  setCurrentRun(runId, status) {
    set({ currentRunId: runId, currentRunStatus: status });
  },

  setRunStatus(status) {
    set({ currentRunStatus: status });
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
      case "run_completed": {
        next.currentRunStatus = "completed";
        break;
      }
      case "run_failed": {
        next.currentRunStatus = "failed";
        break;
      }
      case "run_aborted": {
        next.currentRunStatus = "aborted";
        break;
      }
    }

    set(next as PlatformState);
  },
}));
