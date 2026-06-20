import { usePlatformStore } from "@/platformStore";
import { useStore } from "@/store";
import type { Workflow, WorkflowNode } from "@/types";

function patchNodeParams(
  workflow: Workflow,
  nodeId: string,
  paramsPatch: Record<string, unknown>,
): Workflow {
  return {
    ...workflow,
    nodes: workflow.nodes.map((node) =>
      node.id === nodeId
        ? { ...node, params: { ...node.params, ...paramsPatch } }
        : node,
    ),
  };
}

export function updateNodeParams(
  nodeId: string,
  paramsPatch: Record<string, unknown>,
): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;

  const next = patchNodeParams(workflow, nodeId, paramsPatch);
  useStore.setState({ workflow: next });

  const platformId = usePlatformStore.getState().currentWorkflowId;
  if (platformId) {
    usePlatformStore.setState({
      currentWorkflow: next,
    });
  }
  usePlatformStore.getState().markWorkflowDirty();
}

export function getNodeParam(
  node: WorkflowNode,
  key: string,
): unknown {
  return node.params?.[key];
}
