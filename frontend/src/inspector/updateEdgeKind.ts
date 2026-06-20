import { usePlatformStore } from "@/platformStore";
import { useStore } from "@/store";
import type { Workflow, WorkflowEdge } from "@/types";

function patchEdge(
  workflow: Workflow,
  edgeId: string,
  kind: WorkflowEdge["kind"],
): Workflow {
  return {
    ...workflow,
    edges: workflow.edges.map((edge) =>
      edge.id === edgeId ? { ...edge, kind } : edge,
    ),
  };
}

export function updateEdgeKind(
  edgeId: string,
  kind: WorkflowEdge["kind"],
): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;
  const next = patchEdge(workflow, edgeId, kind);
  useStore.setState({ workflow: next });
  const platformId = usePlatformStore.getState().currentWorkflowId;
  if (platformId) {
    usePlatformStore.setState({ currentWorkflow: next });
  }
  usePlatformStore.getState().markWorkflowDirty();
}
