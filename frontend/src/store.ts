import { create } from "zustand";
import type {
  NodeRuntimeState,
  RunEvent,
  Workflow,
} from "./types";

export type RunStatus = "idle" | "running" | "completed" | "failed";

interface State {
  workflow: Workflow | null;
  runStatus: RunStatus;
  nodeStates: Record<string, NodeRuntimeState>;
  logs: RunEvent[];
  selectedNodeId: string | null;
  setWorkflow(wf: Workflow): void;
  applyEvent(ev: RunEvent): void;
  resetRun(): void;
  setRunStatus(status: RunStatus): void;
  selectNode(id: string | null): void;
}

function freshNodeStates(wf: Workflow): Record<string, NodeRuntimeState> {
  const out: Record<string, NodeRuntimeState> = {};
  for (const node of wf.nodes) {
    out[node.id] = { status: "idle" };
  }
  return out;
}

export const useStore = create<State>((set, get) => ({
  workflow: null,
  runStatus: "idle",
  nodeStates: {},
  logs: [],
  selectedNodeId: null,

  setWorkflow(wf) {
    set({
      workflow: wf,
      nodeStates: freshNodeStates(wf),
      logs: [],
      runStatus: "idle",
      selectedNodeId: null,
    });
  },

  resetRun() {
    const wf = get().workflow;
    set({
      runStatus: "idle",
      nodeStates: wf ? freshNodeStates(wf) : {},
      logs: [],
      selectedNodeId: null,
    });
  },

  setRunStatus(status) {
    set({ runStatus: status });
  },

  selectNode(id) {
    set({ selectedNodeId: id });
  },

  applyEvent(ev) {
    const prevLogs = get().logs;
    const prevStates = get().nodeStates;
    const next: Partial<State> = {
      logs: [...prevLogs, ev],
    };

    switch (ev.event) {
      case "run_started": {
        const wf = get().workflow;
        next.runStatus = "running";
        next.nodeStates = wf ? freshNodeStates(wf) : {};
        next.selectedNodeId = null;
        break;
      }
      case "node_started": {
        if (ev.node_id) {
          const prev = prevStates[ev.node_id] ?? { status: "idle" };
          next.nodeStates = {
            ...prevStates,
            [ev.node_id]: {
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
        if (ev.node_id) {
          const prev = prevStates[ev.node_id] ?? { status: "running" };
          next.nodeStates = {
            ...prevStates,
            [ev.node_id]: { ...prev, status: "running", message: ev.message },
          };
        }
        break;
      }
      case "node_completed": {
        if (ev.node_id) {
          const prev = prevStates[ev.node_id] ?? { status: "idle" };
          next.nodeStates = {
            ...prevStates,
            [ev.node_id]: {
              ...prev,
              status: "success",
              message: undefined,
              output: ev.output,
            },
          };
        }
        break;
      }
      case "node_failed": {
        if (ev.node_id) {
          const prev = prevStates[ev.node_id] ?? { status: "idle" };
          next.nodeStates = {
            ...prevStates,
            [ev.node_id]: {
              ...prev,
              status: "error",
              message: ev.error ?? ev.message,
              error: ev.error,
            },
          };
        }
        break;
      }
      case "run_completed": {
        next.runStatus = "completed";
        break;
      }
      case "run_failed": {
        next.runStatus = "failed";
        break;
      }
    }

    set(next as State);
  },
}));
