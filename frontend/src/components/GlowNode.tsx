import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Check, AlertTriangle, GitBranch, GitMerge, Ban, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useStore } from "@/store";
import type { NodeRuntimeState, NodeType } from "@/types";
import type { NodePort } from "@/lib/canvasPorts";
import { cn } from "@/lib/utils";

export interface GlowNodeData extends Record<string, unknown> {
  label: string;
  nodeType: NodeType;
  runtime: NodeRuntimeState;
  sourcePorts?: NodePort[];
  targetPorts?: NodePort[];
  dimmed?: boolean;
}

const statusBorder: Record<string, string> = {
  idle: "border-border",
  running: "border-primary animate-pulse-halo",
  success: "border-emerald-500",
  error: "border-destructive",
  skipped: "border-muted-foreground/40 border-dashed",
  waiting: "border-amber-500/70",
};

const typeBackground: Partial<Record<NodeType, string>> = {
  start: "bg-emerald-950/40",
  end: "bg-red-950/40",
  condition: "bg-amber-950/40",
  switch: "bg-violet-950/40",
  merge: "bg-cyan-950/40",
};

function TypeIcon({ nodeType }: { nodeType: NodeType }) {
  if (nodeType === "condition") {
    return <GitBranch className="mr-1 inline h-3 w-3 text-amber-400" />;
  }
  if (nodeType === "switch") {
    return <GitBranch className="mr-1 inline h-3 w-3 text-violet-400" />;
  }
  if (nodeType === "merge") {
    return <GitMerge className="mr-1 inline h-3 w-3 text-cyan-400" />;
  }
  return null;
}

function PortHandles({
  ports,
  type,
  position,
}: {
  ports: NodePort[];
  type: "source" | "target";
  position: Position;
}) {
  if (ports.length <= 1) {
    return (
      <Handle
        type={type}
        position={position}
        id={ports[0]?.id}
        className="!h-2 !w-2 !border-2 !bg-background"
      />
    );
  }

  return (
    <>
      {ports.map((port, index) => {
        const pct =
          ports.length === 1 ? 50 : (index / (ports.length - 1)) * 100;
        return (
          <div
            key={port.id}
            className="pointer-events-none absolute"
            style={{
              left: `${pct}%`,
              ...(position === Position.Top
                ? { top: 0, transform: "translate(-50%, -50%)" }
                : { bottom: 0, transform: "translate(-50%, 50%)" }),
            }}
          >
            <span
              className={cn(
                "absolute left-1/2 max-w-[72px] -translate-x-1/2 truncate text-[9px] text-muted-foreground",
                position === Position.Top ? "-top-4" : "top-3",
              )}
              title={port.label}
            >
              {port.label}
            </span>
            <Handle
              type={type}
              position={position}
              id={port.id}
              className="pointer-events-auto !h-2 !w-2 !border-2 !bg-background"
            />
          </div>
        );
      })}
    </>
  );
}

export function GlowNode({ id, data }: NodeProps) {
  const { t } = useTranslation();
  const { label, nodeType, runtime, sourcePorts, targetPorts, dimmed } =
    data as GlowNodeData;
  const status = runtime?.status ?? "idle";
  const message = runtime?.message;
  const selectedId = useStore((s) => s.selectedNodeId);
  const isSelected = selectedId === id;
  const hasOutput =
    runtime?.output !== undefined && runtime?.output !== null;
  const mergeWaiting = runtime?.mergeWaiting;

  const sources = sourcePorts ?? [];
  const targets = targetPorts ?? [];

  return (
    <div
      className={cn(
        "relative min-w-[180px] rounded-lg border bg-card px-4 py-3 text-center text-card-foreground transition-colors",
        statusBorder[status],
        typeBackground[nodeType],
        isSelected && "outline outline-2 outline-offset-2 outline-primary",
        dimmed && "opacity-40",
      )}
    >
      <PortHandles ports={targets} type="target" position={Position.Top} />
      {status === "success" && (
        <Check className="absolute right-2 top-2 h-3.5 w-3.5 text-emerald-500" />
      )}
      {status === "error" && (
        <AlertTriangle className="absolute right-2 top-2 h-3.5 w-3.5 text-destructive" />
      )}
      {status === "skipped" && (
        <Ban className="absolute right-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
      )}
      {status === "waiting" && (
        <Clock className="absolute right-2 top-2 h-3.5 w-3.5 text-amber-500" />
      )}
      <span className="mb-1 flex items-center justify-center text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <TypeIcon nodeType={nodeType} />
        {nodeType}
      </span>
      <div className="text-sm font-medium">{label}</div>
      {status === "running" && message && (
        <div className="mt-1 text-xs italic text-primary">{message}</div>
      )}
      {status === "waiting" && mergeWaiting && (
        <div className="mt-1 text-xs text-amber-500">
          {t("graph.mergeWaiting", {
            arrived: mergeWaiting.arrived,
            expected: mergeWaiting.expected,
          })}
        </div>
      )}
      {status === "skipped" && (
        <div className="mt-1 text-xs text-muted-foreground">
          {t("graph.nodeSkipped")}
        </div>
      )}
      {status === "success" && hasOutput && (
        <div className="mt-1 text-[10px] text-muted-foreground">
          {t("graph.clickToView")}
        </div>
      )}
      <PortHandles ports={sources} type="source" position={Position.Bottom} />
    </div>
  );
}
