import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EdgeInsertMenu } from "@/components/EdgeInsertMenu";
import { cn } from "@/lib/utils";
import { useStore } from "@/store";

export type InsertableEdgeData = {
  label?: string;
  stroke?: string;
  strokeWidth?: number;
  strokeDasharray?: string;
  opacity?: number;
};

export function InsertableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) {
  const { t } = useTranslation();
  const selectedEdgeId = useStore((s) => s.selectedEdgeId);
  const isSelected = selectedEdgeId === id;
  const edgeData = (data ?? {}) as InsertableEdgeData;

  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: edgeData.stroke,
          strokeWidth: isSelected ? 2.5 : edgeData.strokeWidth,
          strokeDasharray: edgeData.strokeDasharray,
          opacity: edgeData.opacity,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className={cn(
            "nodrag nopan pointer-events-auto absolute flex flex-col items-center gap-0.5",
          )}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            opacity: edgeData.opacity ?? 1,
          }}
        >
          {edgeData.label ? (
            <span className="rounded bg-card/90 px-1 text-[10px] text-muted-foreground">
              {edgeData.label}
            </span>
          ) : null}
          <EdgeInsertMenu edgeId={id}>
            <button
              type="button"
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-full border bg-card text-muted-foreground shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground",
                isSelected && "border-primary text-primary ring-2 ring-primary/30",
              )}
              title={t("graph.insertOnEdge")}
              aria-label={t("graph.insertOnEdge")}
            >
              <Plus className="h-3 w-3" />
            </button>
          </EdgeInsertMenu>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
