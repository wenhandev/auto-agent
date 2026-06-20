import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { apiClient } from "@/api-platform";
import { usePlatformStore } from "@/platformStore";
import { useStore } from "@/store";
import {
  buildOutputShapeTree,
  getPredecessorIds,
} from "./variableUtils";
import { VariableTreeList } from "./VariableTree";

interface AvailableVariablesTabProps {
  nodeId: string;
  onInsert?: (token: string) => void;
}

export function AvailableVariablesTab({
  nodeId,
  onInsert,
}: AvailableVariablesTabProps) {
  const { t } = useTranslation();
  const workflowId = usePlatformStore((s) => s.currentWorkflowId);
  const workflow = useStore((s) => s.workflow);

  const predecessors = useMemo(() => {
    if (!workflow) return new Set<string>();
    return getPredecessorIds(nodeId, workflow.edges);
  }, [workflow, nodeId]);

  const shapesQuery = useQuery({
    queryKey: ["workflows", workflowId, "last-output-shapes"],
    queryFn: () => apiClient.workflows.getLastOutputShapes(workflowId!),
    enabled: !!workflowId,
  });

  const predecessorTrees = useMemo(() => {
    if (!workflow || !shapesQuery.data) return [];
    const shapes = shapesQuery.data.shapes;
    const nodesById = new Map(workflow.nodes.map((n) => [n.id, n]));

    return [...predecessors]
      .filter((id) => shapes[id] !== undefined)
      .sort()
      .map((id) => {
        const node = nodesById.get(id);
        return {
          id,
          label: node?.label ?? id,
          tree: buildOutputShapeTree(shapes[id]),
        };
      });
  }, [workflow, shapesQuery.data, predecessors]);

  const handleSelect = (token: string) => {
    if (onInsert) {
      onInsert(token);
      return;
    }
    void navigator.clipboard.writeText(token).then(() => {
      toast.success(t("nodeInspector.tokenCopied"));
    });
  };

  if (shapesQuery.isLoading) {
    return (
      <div className="py-6 text-center text-xs text-muted-foreground">
        {t("nodeInspector.variablesLoading")}
      </div>
    );
  }

  if (shapesQuery.isError) {
    return (
      <div className="py-6 text-center text-xs text-destructive">
        {(shapesQuery.error as Error).message}
      </div>
    );
  }

  const hasRun = !!shapesQuery.data?.run_id;
  if (!hasRun || predecessorTrees.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
        {t("nodeInspector.variablesEmpty")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {shapesQuery.data?.started_at && (
        <div className="text-[10px] text-muted-foreground">
          {t("nodeInspector.variablesFromRun", {
            runId: shapesQuery.data.run_id,
          })}
        </div>
      )}
      <VariableTreeList
        predecessors={predecessorTrees}
        onSelect={handleSelect}
      />
    </div>
  );
}

export function useVariablePredecessors(nodeId: string) {
  const workflow = useStore((s) => s.workflow);
  const workflowId = usePlatformStore((s) => s.currentWorkflowId);

  const predecessors = useMemo(() => {
    if (!workflow) return new Set<string>();
    return getPredecessorIds(nodeId, workflow.edges);
  }, [workflow, nodeId]);

  const shapesQuery = useQuery({
    queryKey: ["workflows", workflowId, "last-output-shapes"],
    queryFn: () => apiClient.workflows.getLastOutputShapes(workflowId!),
    enabled: !!workflowId,
  });

  const predecessorTrees = useMemo(() => {
    if (!workflow || !shapesQuery.data) return [];
    const shapes = shapesQuery.data.shapes;
    const nodesById = new Map(workflow.nodes.map((n) => [n.id, n]));

    return [...predecessors]
      .filter((id) => shapes[id] !== undefined)
      .sort()
      .map((id) => {
        const node = nodesById.get(id);
        return {
          id,
          label: node?.label ?? id,
          tree: buildOutputShapeTree(shapes[id]),
        };
      });
  }, [workflow, shapesQuery.data, predecessors]);

  const shapes = shapesQuery.data?.shapes ?? {};

  return { predecessors, predecessorTrees, shapes, shapesQuery };
}
