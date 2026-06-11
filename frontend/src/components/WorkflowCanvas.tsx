import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import dagre from "dagre";
import { useTranslation } from "react-i18next";
import { useStore } from "@/store";
import { GlowNode, type GlowNodeData } from "./GlowNode";
import { NodeInspector } from "./NodeInspector";
import type { NodeRuntimeState, Workflow } from "@/types";

const NODE_WIDTH = 200;
const NODE_HEIGHT = 80;

const nodeTypes: NodeTypes = { glow: GlowNode };

function layout(workflow: Workflow): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", ranksep: 80, nodesep: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of workflow.nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of workflow.edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const positions: Record<string, { x: number; y: number }> = {};
  for (const node of workflow.nodes) {
    const pos = g.node(node.id);
    positions[node.id] = {
      x: pos.x - NODE_WIDTH / 2,
      y: pos.y - NODE_HEIGHT / 2,
    };
  }
  return positions;
}

export function WorkflowCanvas() {
  const { t } = useTranslation();
  const workflow = useStore((s) => s.workflow);
  const nodeStates = useStore((s) => s.nodeStates);
  const selectNode = useStore((s) => s.selectNode);

  const positions = useMemo(
    () => (workflow ? layout(workflow) : {}),
    [workflow],
  );

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      selectNode(node.id);
    },
    [selectNode],
  );

  const onPaneClick = useCallback(() => selectNode(null), [selectNode]);

  const flowNodes = useMemo<Node<GlowNodeData>[]>(() => {
    if (!workflow) return [];
    return workflow.nodes.map((w) => {
      const runtime: NodeRuntimeState =
        nodeStates[w.id] ?? { status: "idle" };
      return {
        id: w.id,
        type: "glow",
        position: positions[w.id] ?? { x: 0, y: 0 },
        data: {
          label: w.label,
          nodeType: w.type,
          runtime,
        },
      };
    });
  }, [workflow, nodeStates, positions]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!workflow) return [];
    return workflow.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      animated: false,
      label: e.when ?? undefined,
      style: { stroke: "hsl(var(--muted-foreground) / 0.5)" },
    }));
  }, [workflow]);

  if (!workflow) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {t("graph.loadingWorkflow")}
      </div>
    );
  }

  return (
    <>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
      >
        <Background color="hsl(var(--border))" gap={16} />
        <Controls />
      </ReactFlow>
      <NodeInspector />
    </>
  );
}
