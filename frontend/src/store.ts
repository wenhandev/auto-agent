import { create } from "zustand";
import type {
  NodeRuntimeState,
  RunEvent,
  Workflow,
} from "./types";

export type RunStatus = "idle" | "running" | "completed" | "failed" | "aborted";

interface State {
  workflow: Workflow | null;
  runStatus: RunStatus;
  nodeStates: Record<string, NodeRuntimeState>;
  prunedEdgeIds: Set<string>;
  logs: RunEvent[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  setWorkflow(wf: Workflow): void;
  /** Update graph structure without clearing run logs, node states, or selection. */
  syncWorkflowGraph(wf: Workflow): void;
  /** Full reset for replay initial load. */
  resetWorkflowForReplay(wf: Workflow): void;
  applyEvent(ev: RunEvent): void;
  resetRun(): void;
  setRunStatus(status: RunStatus): void;
  selectNode(id: string | null): void;
  selectEdge(id: string | null): void;
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
  prunedEdgeIds: new Set(),
  logs: [],
  selectedNodeId: null,
  selectedEdgeId: null,

  setWorkflow(wf) {
    set({
      workflow: wf,
      nodeStates: freshNodeStates(wf),
      prunedEdgeIds: new Set(),
      logs: [],
      runStatus: "idle",
      selectedNodeId: null,
      selectedEdgeId: null,
    });
  },

  syncWorkflowGraph(wf) {
    set({ workflow: wf });
  },

  resetWorkflowForReplay(wf) {
    set({
      workflow: wf,
      nodeStates: freshNodeStates(wf),
      prunedEdgeIds: new Set(),
      logs: [],
      runStatus: "idle",
      selectedNodeId: null,
      selectedEdgeId: null,
    });
  },

  resetRun() {
    const wf = get().workflow;
    set({
      runStatus: "idle",
      nodeStates: wf ? freshNodeStates(wf) : {},
      prunedEdgeIds: new Set(),
      logs: [],
      selectedNodeId: null,
      selectedEdgeId: null,
    });
  },

  setRunStatus(status) {
    set({ runStatus: status });
  },

  selectNode(id) {
    set({ selectedNodeId: id, selectedEdgeId: null });
  },

  selectEdge(id) {
    set({ selectedEdgeId: id, selectedNodeId: null });
  },

  applyEvent(ev) {
    const prevLogs = get().logs;
    const prevStates = get().nodeStates;
    const prevPruned = get().prunedEdgeIds;
    const next: Partial<State> = {
      logs: [...prevLogs, ev],
    };

    switch (ev.event) {
      case "run_started": {
        const wf = get().workflow;
        next.runStatus = "running";
        next.nodeStates = wf ? freshNodeStates(wf) : {};
        next.prunedEdgeIds = new Set();
        next.selectedNodeId = null;
        next.selectedEdgeId = null;
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
              mergeWaiting: undefined,
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
              mergeWaiting: undefined,
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
              mergeWaiting: undefined,
            },
          };
        }
        break;
      }
      case "node_skipped": {
        if (ev.node_id) {
          next.nodeStates = {
            ...prevStates,
            [ev.node_id]: {
              status: "skipped",
              message: ev.message,
            },
          };
        }
        break;
      }
      case "merge_waiting": {
        if (ev.node_id) {
          const prev = prevStates[ev.node_id] ?? { status: "idle" };
          const arrived = ev.arrived ?? 0;
          const expected = ev.expected ?? 0;
          next.nodeStates = {
            ...prevStates,
            [ev.node_id]: {
              ...prev,
              status: "waiting",
              mergeWaiting: { arrived, expected },
              message: undefined,
            },
          };
        }
        break;
      }
      case "branch_pruned": {
        const edgeId = ev.edge_id;
        if (edgeId) {
          const pruned = new Set(prevPruned);
          pruned.add(edgeId);
          next.prunedEdgeIds = pruned;
        }
        break;
      }
      case "run_completed": {
        next.runStatus = "completed";
        break;
      }
      case "run_completed_with_errors": {
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
