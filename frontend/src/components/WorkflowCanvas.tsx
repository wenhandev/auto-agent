import { useCallback, useEffect, useMemo, useRef, type MouseEvent } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  useStore as useFlowStore,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import dagre from "dagre";
import { useTheme } from "next-themes";
import { useTranslation } from "react-i18next";
import { useStore } from "@/store";
import { GlowNode, type GlowNodeData } from "./GlowNode";
import { InsertableEdge } from "./InsertableEdge";
import { NodeInspector } from "./NodeInspector";
import { NodeInspectorBoundary } from "./NodeInspectorBoundary";
import { NodePalette } from "./NodePalette";
import { usePlatformStore } from "@/platformStore";
import type { NodeRuntimeState, NodeType, Workflow, WorkflowEdge } from "@/types";
import {
  getSourcePorts,
  getTargetPorts,
  nodeLayoutHeight,
  usesSourceHandles,
  usesTargetHandles,
} from "@/lib/canvasPorts";
import {
  computeWorkflowViewport,
  WORKFLOW_CANVAS_PADDING,
  type LayoutBounds,
} from "@/lib/workflowViewport";
import { workflowEdgeLabel } from "@/lib/edgeLabels";

const NODE_WIDTH = 200;

const nodeTypes: NodeTypes = { glow: GlowNode };
const edgeTypes = { insertable: InsertableEdge };

function miniMapNodeColor(node: Node<GlowNodeData>): string {
  const status = node.data?.runtime?.status ?? "idle";
  switch (status) {
    case "running":
      return "#e4e4e7";
    case "success":
      return "#34d399";
    case "error":
      return "#f87171";
    case "waiting":
      return "#fbbf24";
    case "skipped":
      return "#52525b";
    default:
      return "#a1a1aa";
  }
}

function layout(workflow: Workflow): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", ranksep: 80, nodesep: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of workflow.nodes) {
    g.setNode(node.id, {
      width: NODE_WIDTH,
      height: nodeLayoutHeight(node, workflow),
    });
  }
  for (const edge of workflow.edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const positions: Record<string, { x: number; y: number }> = {};
  for (const node of workflow.nodes) {
    const pos = g.node(node.id);
    const height = nodeLayoutHeight(node, workflow);
    positions[node.id] = {
      x: pos.x - NODE_WIDTH / 2,
      y: pos.y - height / 2,
    };
  }
  return positions;
}

function edgeLabel(
  edge: WorkflowEdge,
  sourceNodeType: NodeType | undefined,
  t: ReturnType<typeof useTranslation>["t"],
): string | undefined {
  return workflowEdgeLabel(edge, sourceNodeType, t);
}

const FIT_PADDING = WORKFLOW_CANVAS_PADDING;

function layoutBounds(
  workflow: Workflow,
  positions: Record<string, { x: number; y: number }>,
): LayoutBounds {
  if (workflow.nodes.length === 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const node of workflow.nodes) {
    const pos = positions[node.id] ?? { x: 0, y: 0 };
    const height = nodeLayoutHeight(node, workflow);
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + NODE_WIDTH);
    maxY = Math.max(maxY, pos.y + height);
  }

  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

function FitViewFromLayout({
  fitKey,
  bounds,
}: {
  fitKey: string;
  bounds: LayoutBounds;
}) {
  const { setViewport } = useReactFlow();
  const flowWidth = useFlowStore((s) => s.width);
  const flowHeight = useFlowStore((s) => s.height);
  const lastFitKey = useRef<string | null>(null);

  useEffect(() => {
    if (bounds.width <= 0 || bounds.height <= 0) return;
    if (flowWidth <= 0 || flowHeight <= 0) return;
    if (lastFitKey.current === fitKey) return;

    let cancelled = false;
    const frame = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (cancelled) return;
        const viewport = computeWorkflowViewport(bounds, flowWidth, flowHeight, {
          padding: FIT_PADDING,
          nodeWidth: NODE_WIDTH,
        });
        setViewport(viewport, { duration: 0 });
        lastFitKey.current = fitKey;
      });
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [fitKey, bounds, flowWidth, flowHeight, setViewport]);

  return null;
}

function WorkflowControls({ bounds }: { bounds: LayoutBounds }) {
  const { setViewport } = useReactFlow();
  const flowWidth = useFlowStore((s) => s.width);
  const flowHeight = useFlowStore((s) => s.height);

  const onFitView = useCallback(() => {
    if (bounds.width <= 0 || bounds.height <= 0) return;
    if (flowWidth <= 0 || flowHeight <= 0) return;
    const viewport = computeWorkflowViewport(bounds, flowWidth, flowHeight, {
      padding: FIT_PADDING,
      nodeWidth: NODE_WIDTH,
    });
    setViewport(viewport, { duration: 200 });
  }, [bounds, flowWidth, flowHeight, setViewport]);

  return <Controls onFitView={onFitView} />;
}

export function WorkflowCanvas({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();
  const workflow = useStore((s) => s.workflow);
  const versionKey = usePlatformStore(
    (s) => s.currentVersion?.id ?? s.currentWorkflowId ?? "workflow",
  );
  const fitKey = `${versionKey}:${workflow?.nodes.length ?? 0}`;
  const nodeStates = useStore((s) => s.nodeStates);
  const prunedEdgeIds = useStore((s) => s.prunedEdgeIds);
  const selectNode = useStore((s) => s.selectNode);
  const selectEdge = useStore((s) => s.selectEdge);
  const selectedEdgeId = useStore((s) => s.selectedEdgeId);

  const positions = useMemo(
    () => (workflow ? layout(workflow) : {}),
    [workflow],
  );

  const bounds = useMemo(
    () => (workflow ? layoutBounds(workflow, positions) : { x: 0, y: 0, width: 0, height: 0 }),
    [workflow, positions],
  );

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      selectNode(node.id);
    },
    [selectNode],
  );

  const onNodeDoubleClick = useCallback(
    (event: MouseEvent, node: Node) => {
      event.stopPropagation();
      selectNode(node.id);
    },
    [selectNode],
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
    selectEdge(null);
  }, [selectNode, selectEdge]);

  const onEdgeClick = useCallback(
    (_: unknown, edge: Edge) => {
      selectEdge(edge.id);
    },
    [selectEdge],
  );

  const flowNodes = useMemo<Node<GlowNodeData>[]>(() => {
    if (!workflow) return [];
    return workflow.nodes.map((w) => {
      const runtime: NodeRuntimeState =
        nodeStates[w.id] ?? { status: "idle" };
      const outCount = workflow.edges.filter((e) => e.source === w.id).length;
      const inCount = workflow.edges.filter((e) => e.target === w.id).length;
      const height = nodeLayoutHeight(w, workflow);
      return {
        id: w.id,
        type: "glow",
        position: positions[w.id] ?? { x: 0, y: 0 },
        width: NODE_WIDTH,
        height,
        data: {
          label: w.label,
          nodeType: w.type,
          runtime,
          dimmed: runtime.status === "skipped",
          sourcePorts: usesSourceHandles(w.type, outCount)
            ? getSourcePorts(w.id, workflow, t)
            : undefined,
          targetPorts: usesTargetHandles(w.type, inCount)
            ? getTargetPorts(w.id, workflow)
            : undefined,
        },
      };
    });
  }, [workflow, nodeStates, positions, t]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!workflow) return [];
    const nodesById = Object.fromEntries(workflow.nodes.map((n) => [n.id, n]));

    return workflow.edges.map((e) => {
      const sourceNode = nodesById[e.source];
      const targetNode = nodesById[e.target];
      const outCount = workflow.edges.filter((ed) => ed.source === e.source).length;
      const inCount = workflow.edges.filter((ed) => ed.target === e.target).length;
      const isOnError = e.kind === "on_error";
      const isPruned = prunedEdgeIds.has(e.id);
      const isSelected = selectedEdgeId === e.id;

      return {
        id: e.id,
        type: "insertable",
        source: e.source,
        target: e.target,
        sourceHandle: usesSourceHandles(sourceNode?.type ?? "set", outCount)
          ? e.id
          : undefined,
        targetHandle: usesTargetHandles(targetNode?.type ?? "set", inCount)
          ? e.id
          : undefined,
        animated: false,
        data: {
          label: edgeLabel(e, sourceNode?.type, t),
          stroke: isOnError
            ? "hsl(var(--destructive) / 0.85)"
            : isSelected
              ? "hsl(var(--primary))"
              : "hsl(var(--muted-foreground) / 0.5)",
          strokeWidth: isOnError ? 2 : 1,
          strokeDasharray: isOnError ? "6 4" : undefined,
          opacity: isPruned ? 0.3 : 1,
        },
      };
    });
  }, [workflow, prunedEdgeIds, selectedEdgeId, t]);

  if (!workflow) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {t("graph.loadingWorkflow")}
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        colorMode={resolvedTheme === "light" ? "light" : "dark"}
        className="h-full w-full"
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={1.5}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
        onNodeClick={readOnly ? undefined : onNodeClick}
        onNodeDoubleClick={readOnly ? undefined : onNodeDoubleClick}
        onPaneClick={readOnly ? undefined : onPaneClick}
        onEdgeClick={readOnly ? undefined : onEdgeClick}
      >
        <FitViewFromLayout fitKey={fitKey} bounds={bounds} />
        <Background color="hsl(var(--border))" gap={16} />
        <WorkflowControls bounds={bounds} />
        <MiniMap
          pannable
          zoomable
          ariaLabel={t("graph.minimap")}
          nodeColor={miniMapNodeColor}
          nodeStrokeColor="#d4d4d8"
          nodeStrokeWidth={1}
          nodeBorderRadius={4}
          maskColor="rgba(0, 0, 0, 0.55)"
          maskStrokeColor="#fafafa"
          maskStrokeWidth={1}
          style={{ width: 200, height: 140 }}
          className="!m-3 overflow-hidden !rounded-lg !border !border-border !shadow-lg"
        />
      </ReactFlow>
      {!readOnly && <NodePalette />}
      {!readOnly && (
        <NodeInspectorBoundary>
          <NodeInspector />
        </NodeInspectorBoundary>
      )}
    </div>
  );
}
