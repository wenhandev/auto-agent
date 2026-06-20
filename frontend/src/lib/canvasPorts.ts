import type { TFunction } from "i18next";
import type { NodeType, Workflow, WorkflowEdge } from "@/types";
import { workflowEdgeLabel } from "@/lib/edgeLabels";

export interface NodePort {
  id: string;
  label: string;
}

function edgeSourceLabel(
  edge: WorkflowEdge,
  sourceNodeType: NodeType | undefined,
  t: TFunction,
): string {
  return (
    workflowEdgeLabel(edge, sourceNodeType, t) ?? t("graph.edgeNext")
  );
}

export function getSourcePorts(
  nodeId: string,
  workflow: Workflow,
  t: TFunction,
): NodePort[] {
  const sourceNode = workflow.nodes.find((n) => n.id === nodeId);
  return workflow.edges
    .filter((e) => e.source === nodeId)
    .map((e) => ({
      id: e.id,
      label: edgeSourceLabel(e, sourceNode?.type, t),
    }));
}

export function getTargetPorts(
  nodeId: string,
  workflow: Workflow,
): NodePort[] {
  return workflow.edges
    .filter((e) => e.target === nodeId)
    .map((e) => ({
      id: e.id,
      label: workflow.nodes.find((n) => n.id === e.source)?.label ?? e.source,
    }));
}

export function usesSourceHandles(nodeType: NodeType, outCount: number): boolean {
  return (
    outCount > 1 ||
    nodeType === "switch" ||
    nodeType === "condition"
  );
}

export function usesTargetHandles(nodeType: NodeType, inCount: number): boolean {
  return nodeType === "merge" && inCount > 1;
}

export function nodeLayoutHeight(node: { id: string; type: NodeType }, workflow: Workflow): number {
  const base = 80;
  const outCount = workflow.edges.filter((e) => e.source === node.id).length;
  const inCount = workflow.edges.filter((e) => e.target === node.id).length;
  const ports = Math.max(outCount, inCount, 1);
  if (
    node.type === "switch" ||
    node.type === "merge" ||
    node.type === "condition"
  ) {
    return base + Math.max(0, ports - 2) * 14;
  }
  return base;
}
