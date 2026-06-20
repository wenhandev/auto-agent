import type { TFunction } from "i18next";
import type { NodeType, WorkflowEdge } from "@/types";

/** Label for canvas edges / ports; omit on plain sequential connections. */
export function workflowEdgeLabel(
  edge: WorkflowEdge,
  sourceNodeType: NodeType | undefined,
  t: TFunction,
): string | undefined {
  if (edge.kind === "on_error") {
    return t("graph.edgeOnError");
  }
  if (edge.when === "true") return t("graph.edgeTrue");
  if (edge.when === "false") return t("graph.edgeFalse");
  if (sourceNodeType === "switch") {
    if (edge.case !== undefined && edge.case !== null) return edge.case;
    if (edge.case === null) return t("graph.edgeDefault");
  }
  if (edge.case !== undefined && edge.case !== null) {
    return edge.case;
  }
  return undefined;
}
