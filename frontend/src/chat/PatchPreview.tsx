import { useTranslation } from "react-i18next";
import type { PatchOp, Workflow, WorkflowNode } from "@/types-platform";
import { cn } from "@/lib/utils";

interface Props {
  patch: PatchOp[] | null;
  fullWorkflow?: Workflow;
}

type Intent = "add" | "remove" | "update" | "info";

interface Row {
  intent: Intent;
  marker: string;
  text: string;
}

const MARK_ADD = "+";
const MARK_REMOVE = "\u2212";
const MARK_UPDATE = "\u270E";
const MARK_START = "\u25B6";
const MARK_REPLACE = "\u21C6";

function nodeLabel(workflow: Workflow | undefined, id: string): string {
  if (!workflow) return id;
  const n = workflow.nodes.find((node) => node.id === id);
  return n ? n.label : id;
}

function describeUpdate(patch: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof patch.label === "string") parts.push(`label="${patch.label}"`);
  if (typeof patch.type === "string") parts.push(`type=${patch.type}`);
  if (patch.params && typeof patch.params === "object") {
    const keys = Object.keys(patch.params as Record<string, unknown>);
    if (keys.length) parts.push(`params{${keys.join(", ")}}`);
  }
  return parts.length ? parts.join(", ") : "\u2014";
}

function rowsFromPatch(
  patch: PatchOp[],
  workflow: Workflow | undefined,
  t: (k: string, opts?: Record<string, unknown>) => string,
): Row[] {
  return patch.map((op): Row => {
    switch (op.op) {
      case "add_node": {
        const n: WorkflowNode = op.node;
        return {
          intent: "add",
          marker: MARK_ADD,
          text: t("patch.addNode", { type: n.type, label: n.label }),
        };
      }
      case "remove_node": {
        const label = nodeLabel(workflow, op.id);
        return {
          intent: "remove",
          marker: MARK_REMOVE,
          text: t("patch.removeNode", { label }),
        };
      }
      case "update_node": {
        const label = nodeLabel(workflow, op.id);
        return {
          intent: "update",
          marker: MARK_UPDATE,
          text: t("patch.updateNode", {
            label,
            summary: describeUpdate(op.patch),
          }),
        };
      }
      case "add_edge": {
        const s = nodeLabel(workflow, op.edge.source);
        const target = nodeLabel(workflow, op.edge.target);
        return {
          intent: "add",
          marker: MARK_ADD,
          text: t("patch.addEdge", { source: s, target }),
        };
      }
      case "remove_edge": {
        const ref = workflow?.edges.find((e) => e.id === op.id);
        if (ref) {
          const s = nodeLabel(workflow, ref.source);
          const target = nodeLabel(workflow, ref.target);
          return {
            intent: "remove",
            marker: MARK_REMOVE,
            text: t("patch.removeEdge", { source: s, target }),
          };
        }
        return {
          intent: "remove",
          marker: MARK_REMOVE,
          text: t("patch.removeEdgeById", { id: op.id }),
        };
      }
      case "set_start": {
        const label = nodeLabel(workflow, op.id);
        return {
          intent: "info",
          marker: MARK_START,
          text: t("patch.setStart", { label }),
        };
      }
    }
  });
}

const intentClasses: Record<Intent, string> = {
  add: "text-emerald-400",
  remove: "text-destructive",
  update: "text-amber-400",
  info: "text-sky-400",
};

export function PatchPreview({ patch, fullWorkflow }: Props) {
  const { t } = useTranslation();
  if (!patch && !fullWorkflow) return null;

  if (!patch && fullWorkflow) {
    return (
      <div className="mt-2 flex flex-col gap-1 rounded-md border bg-background/40 p-2 text-xs">
        <div className={cn("flex items-center gap-2", intentClasses.info)}>
          <span className="font-mono">{MARK_REPLACE}</span>
          <span>
            {t("patch.fullReplace", { count: fullWorkflow.nodes.length })}
          </span>
        </div>
      </div>
    );
  }

  const rows = rowsFromPatch(patch ?? [], fullWorkflow, t);
  if (!rows.length) return null;

  return (
    <div className="mt-2 flex flex-col gap-1 rounded-md border bg-background/40 p-2 text-xs">
      {rows.map((r, i) => (
        <div
          key={i}
          className={cn("flex items-start gap-2", intentClasses[r.intent])}
        >
          <span className="font-mono">{r.marker}</span>
          <span className="text-foreground/90">{r.text}</span>
        </div>
      ))}
    </div>
  );
}
