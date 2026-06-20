import { usePlatformStore } from "@/platformStore";
import { useStore } from "@/store";
import type { NodeType, Workflow, WorkflowEdge, WorkflowNode } from "@/types";

function applyWorkflow(next: Workflow, selectedNodeId: string | null) {
  useStore.setState({ workflow: next, selectedNodeId });
  const platformId = usePlatformStore.getState().currentWorkflowId;
  if (platformId) {
    usePlatformStore.setState({ currentWorkflow: next });
  }
  usePlatformStore.getState().markWorkflowDirty();
}

function newId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

const DEFAULT_LABELS: Partial<Record<NodeType, string>> = {
  navigate: "Navigate",
  click: "Click",
  fill: "Fill",
  wait: "Wait",
  extract: "Extract",
  fuzzy_action: "Fuzzy action",
  set: "Set",
  filter: "Filter",
  merge: "Merge",
};

function defaultParams(type: NodeType): Record<string, unknown> {
  switch (type) {
    case "navigate":
      return { url: "" };
    case "click":
      return { selector: "" };
    case "fill":
      return { selector: "", value: "" };
    case "wait":
      return { ms: 1000 };
    case "extract":
      return { instruction: "" };
    case "fuzzy_action":
      return { action: "" };
    case "set":
      return { values: {} };
    case "filter":
      return { predicate: "" };
    case "merge":
      return { mode: "append" };
    default:
      return {};
  }
}

function findConnectionSource(
  workflow: Workflow,
  selectedNodeId: string | null,
): string {
  if (selectedNodeId) {
    const selected = workflow.nodes.find((n) => n.id === selectedNodeId);
    if (selected && selected.type !== "end") {
      return selected.id;
    }
  }

  const outgoingSources = new Set(workflow.edges.map((e) => e.source));
  const startId = workflow.start_id;
  if (!outgoingSources.has(startId)) {
    return startId;
  }

  for (let i = workflow.nodes.length - 1; i >= 0; i -= 1) {
    const node = workflow.nodes[i];
    if (node.type === "end") continue;
    if (!outgoingSources.has(node.id)) {
      return node.id;
    }
  }

  for (let i = workflow.nodes.length - 1; i >= 0; i -= 1) {
    if (workflow.nodes[i].type !== "end") {
      return workflow.nodes[i].id;
    }
  }

  return startId;
}

export type PaletteGroup = "browser" | "flow" | "data";

export interface PaletteNodeType {
  type: NodeType;
  group: PaletteGroup;
  labelKey: string;
}

export const INSERTABLE_ACTION_TYPES: PaletteNodeType[] = [
  { type: "navigate", group: "browser", labelKey: "navigate" },
  { type: "click", group: "browser", labelKey: "click" },
  { type: "fill", group: "browser", labelKey: "fill" },
  { type: "wait", group: "browser", labelKey: "wait" },
  { type: "extract", group: "browser", labelKey: "extract" },
  { type: "fuzzy_action", group: "browser", labelKey: "fuzzyAction" },
  { type: "set", group: "data", labelKey: "set" },
  { type: "filter", group: "data", labelKey: "filter" },
  { type: "merge", group: "data", labelKey: "merge" },
];

export const INSERTABLE_FLOW_TYPES: PaletteNodeType[] = [
  { type: "condition", group: "flow", labelKey: "ifCondition" },
  { type: "switch", group: "flow", labelKey: "switch" },
];

export function insertNodeOnEdge(
  edgeId: string,
  type: NodeType,
  label?: string,
): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;

  const edgeIndex = workflow.edges.findIndex((e) => e.id === edgeId);
  if (edgeIndex < 0) return;
  const edge = workflow.edges[edgeIndex];

  const id = newId(type.slice(0, 3));
  const node: WorkflowNode = {
    id,
    type,
    label: label ?? DEFAULT_LABELS[type] ?? type,
    params: defaultParams(type),
  };

  const incoming: WorkflowEdge = {
    id: newId("e"),
    source: edge.source,
    target: id,
    when: edge.when,
    case: edge.case,
    kind: edge.kind,
  };
  const outgoing: WorkflowEdge = {
    id: newId("e"),
    source: id,
    target: edge.target,
  };

  const nextEdges = [...workflow.edges];
  nextEdges.splice(edgeIndex, 1, incoming, outgoing);

  applyWorkflow(
    {
      ...workflow,
      nodes: [...workflow.nodes, node],
      edges: nextEdges,
    },
    id,
  );
  useStore.getState().selectEdge(null);
}

export function insertIfNodeOnEdge(edgeId: string): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;

  const edgeIndex = workflow.edges.findIndex((e) => e.id === edgeId);
  if (edgeIndex < 0) return;
  const edge = workflow.edges[edgeIndex];

  const id = newId("if");
  const falseStub = newId(`${id}_false`);

  const ifNode: WorkflowNode = {
    id,
    type: "condition",
    label: "IF",
    params: {},
  };
  const falseNode: WorkflowNode = {
    id: falseStub,
    type: "wait",
    label: "False",
    params: { ms: 0 },
  };

  const incoming: WorkflowEdge = {
    id: newId("e"),
    source: edge.source,
    target: id,
    when: edge.when,
    case: edge.case,
    kind: edge.kind,
  };
  const trueEdge: WorkflowEdge = {
    id: newId("e"),
    source: id,
    target: edge.target,
    when: "true",
  };
  const falseEdge: WorkflowEdge = {
    id: newId("e"),
    source: id,
    target: falseStub,
    when: "false",
  };

  const nextEdges = [...workflow.edges];
  nextEdges.splice(edgeIndex, 1, incoming, trueEdge, falseEdge);

  applyWorkflow(
    {
      ...workflow,
      nodes: [...workflow.nodes, ifNode, falseNode],
      edges: nextEdges,
    },
    id,
  );
  useStore.getState().selectEdge(null);
}

export function insertSwitchNodeOnEdge(edgeId: string): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;

  const edgeIndex = workflow.edges.findIndex((e) => e.id === edgeId);
  if (edgeIndex < 0) return;
  const edge = workflow.edges[edgeIndex];

  const id = newId("sw");
  const altStub = newId(`${id}_alt`);

  const swNode: WorkflowNode = {
    id,
    type: "switch",
    label: "Switch",
    params: { expr: "{{= 'default' }}" },
  };
  const altNode: WorkflowNode = {
    id: altStub,
    type: "wait",
    label: "Default",
    params: { ms: 0 },
  };

  const incoming: WorkflowEdge = {
    id: newId("e"),
    source: edge.source,
    target: id,
    when: edge.when,
    case: edge.case,
    kind: edge.kind,
  };
  const continueEdge: WorkflowEdge = {
    id: newId("e"),
    source: id,
    target: edge.target,
    case: null,
  };
  const altEdge: WorkflowEdge = {
    id: newId("e"),
    source: id,
    target: altStub,
    case: "alt",
  };

  const nextEdges = [...workflow.edges];
  nextEdges.splice(edgeIndex, 1, incoming, continueEdge, altEdge);

  applyWorkflow(
    {
      ...workflow,
      nodes: [...workflow.nodes, swNode, altNode],
      edges: nextEdges,
    },
    id,
  );
  useStore.getState().selectEdge(null);
}

function resolveInsertEdgeId(): string | null {
  return useStore.getState().selectedEdgeId;
}

export function insertPaletteNodeAtSelection(
  entry: PaletteNodeType,
  label: string,
  edgeId?: string | null,
): void {
  const targetEdgeId = edgeId ?? resolveInsertEdgeId();
  if (targetEdgeId) {
    if (entry.type === "condition") {
      insertIfNodeOnEdge(targetEdgeId);
      return;
    }
    if (entry.type === "switch") {
      insertSwitchNodeOnEdge(targetEdgeId);
      return;
    }
    insertNodeOnEdge(targetEdgeId, entry.type, label);
    return;
  }

  if (entry.type === "condition") {
    insertIfNode();
    return;
  }
  if (entry.type === "switch") {
    insertSwitchNode();
    return;
  }
  insertActionNode(entry.type, label);
}

export function insertActionNode(type: NodeType, label?: string): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;

  const id = newId(type.slice(0, 3));
  const node: WorkflowNode = {
    id,
    type,
    label: label ?? DEFAULT_LABELS[type] ?? type,
    params: defaultParams(type),
  };

  const sourceId = findConnectionSource(
    workflow,
    useStore.getState().selectedNodeId,
  );
  const edge: WorkflowEdge = {
    id: newId("e"),
    source: sourceId,
    target: id,
  };

  applyWorkflow(
    {
      ...workflow,
      nodes: [...workflow.nodes, node],
      edges: [...workflow.edges, edge],
    },
    id,
  );
}

export function replaceNodeParams(
  nodeId: string,
  params: Record<string, unknown>,
): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;
  const next: Workflow = {
    ...workflow,
    nodes: workflow.nodes.map((node) =>
      node.id === nodeId ? { ...node, params } : node,
    ),
  };
  applyWorkflow(next, nodeId);
}

export function insertIfNode(): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;

  const id = newId("if");
  const trueStub = newId(`${id}_true`);
  const falseStub = newId(`${id}_false`);

  const ifNode: WorkflowNode = {
    id,
    type: "condition",
    label: "IF",
    params: {},
  };
  const trueNode: WorkflowNode = {
    id: trueStub,
    type: "wait",
    label: "True",
    params: { ms: 0 },
  };
  const falseNode: WorkflowNode = {
    id: falseStub,
    type: "wait",
    label: "False",
    params: { ms: 0 },
  };

  const edges: WorkflowEdge[] = [
    { id: newId("e"), source: id, target: trueStub, when: "true" },
    { id: newId("e"), source: id, target: falseStub, when: "false" },
  ];

  const sourceId = findConnectionSource(
    workflow,
    useStore.getState().selectedNodeId,
  );
  const incomingEdge: WorkflowEdge = {
    id: newId("e"),
    source: sourceId,
    target: id,
  };

  applyWorkflow(
    {
      ...workflow,
      nodes: [...workflow.nodes, ifNode, trueNode, falseNode],
      edges: [...workflow.edges, incomingEdge, ...edges],
    },
    id,
  );
}

export function insertSwitchNode(): void {
  const workflow = useStore.getState().workflow;
  if (!workflow) return;

  const id = newId("sw");
  const defaultStub = newId(`${id}_default`);

  const swNode: WorkflowNode = {
    id,
    type: "switch",
    label: "Switch",
    params: { expr: "{{= 'default' }}" },
  };
  const defaultNode: WorkflowNode = {
    id: defaultStub,
    type: "wait",
    label: "Default",
    params: { ms: 0 },
  };

  const sourceId = findConnectionSource(
    workflow,
    useStore.getState().selectedNodeId,
  );
  const incomingEdge: WorkflowEdge = {
    id: newId("e"),
    source: sourceId,
    target: id,
  };

  applyWorkflow(
    {
      ...workflow,
      nodes: [...workflow.nodes, swNode, defaultNode],
      edges: [
        ...workflow.edges,
        incomingEdge,
        { id: newId("e"), source: id, target: defaultStub, case: null },
      ],
    },
    id,
  );
}
