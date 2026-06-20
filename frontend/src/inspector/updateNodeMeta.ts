import { usePlatformStore } from "@/platformStore";
import { useStore } from "@/store";
import type { RetryPolicy, Workflow, WorkflowNode } from "@/types";

function patchNode(
  workflow: Workflow,
  nodeId: string,
  patch: Partial<WorkflowNode>,
): Workflow {
  return {
    ...workflow,
    nodes: workflow.nodes.map((node) =>
      node.id === nodeId ? { ...node, ...patch } : node,
    ),
  };
}

function applyWorkflow(next: Workflow): void {
  useStore.setState({ workflow: next });
  const platformId = usePlatformStore.getState().currentWorkflowId;
  if (platformId) {
    usePlatformStore.setState({ currentWorkflow: next });
  }
  usePlatformStore.getState().markWorkflowDirty();
}

export function updateNodeMeta(
  nodeId: string,
  patch: Partial<Pick<WorkflowNode, "retry" | "on_error">>,
): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;
  applyWorkflow(patchNode(workflow, nodeId, patch));
}

export function updateNodeRetry(
  nodeId: string,
  retry: RetryPolicy | null,
): void {
  updateNodeMeta(nodeId, { retry });
}

export function updateNodeOnError(
  nodeId: string,
  onError: WorkflowNode["on_error"],
): void {
  updateNodeMeta(nodeId, { on_error: onError });
}
