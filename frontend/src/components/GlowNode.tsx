import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Check, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useStore } from "@/store";
import type { NodeRuntimeState, NodeType } from "@/types";
import { cn } from "@/lib/utils";

export interface GlowNodeData extends Record<string, unknown> {
  label: string;
  nodeType: NodeType;
  runtime: NodeRuntimeState;
}

const statusBorder: Record<string, string> = {
  idle: "border-border",
  running: "border-primary animate-pulse-halo",
  success: "border-emerald-500",
  error: "border-destructive",
};

const typeBackground: Partial<Record<NodeType, string>> = {
  start: "bg-emerald-950/40",
  end: "bg-red-950/40",
  condition: "bg-amber-950/40",
};

export function GlowNode({ id, data }: NodeProps) {
  const { t } = useTranslation();
  const { label, nodeType, runtime } = data as GlowNodeData;
  const status = runtime?.status ?? "idle";
  const message = runtime?.message;
  const selectedId = useStore((s) => s.selectedNodeId);
  const isSelected = selectedId === id;
  const hasOutput =
    runtime?.output !== undefined && runtime?.output !== null;

  return (
    <div
      className={cn(
        "relative min-w-[180px] rounded-lg border bg-card px-4 py-3 text-center text-card-foreground transition-colors",
        statusBorder[status],
        typeBackground[nodeType],
        isSelected && "outline outline-2 outline-offset-2 outline-primary",
      )}
    >
      <Handle type="target" position={Position.Top} />
      {status === "success" && (
        <Check className="absolute right-2 top-2 h-3.5 w-3.5 text-emerald-500" />
      )}
      {status === "error" && (
        <AlertTriangle className="absolute right-2 top-2 h-3.5 w-3.5 text-destructive" />
      )}
      <span className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {nodeType}
      </span>
      <div className="text-sm font-medium">{label}</div>
      {status === "running" && message && (
        <div className="mt-1 text-xs italic text-primary">{message}</div>
      )}
      {status === "success" && hasOutput && (
        <div className="mt-1 text-[10px] text-muted-foreground">
          {t("graph.clickToView")}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
