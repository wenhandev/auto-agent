import { useTranslation } from "react-i18next";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useStore } from "@/store";
import type { WorkflowEdge } from "@/types";
import { updateEdgeKind } from "./updateEdgeKind";

interface Props {
  nodeId: string;
}

export function OutgoingEdgesSection({ nodeId }: Props) {
  const { t } = useTranslation();
  const workflow = useStore((s) => s.workflow);

  if (!workflow) return null;

  const outgoing = workflow.edges.filter((e) => e.source === nodeId);
  if (!outgoing.length) return null;

  const targetLabel = (edge: WorkflowEdge) => {
    const target = workflow.nodes.find((n) => n.id === edge.target);
    return target ? `${target.label} (${edge.target})` : edge.target;
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t("nodeInspector.outgoingEdgesTitle")}
      </div>
      {outgoing.map((edge) => (
        <div key={edge.id} className="flex flex-col gap-1 rounded-md border p-2">
          <Label className="truncate text-xs">{targetLabel(edge)}</Label>
          <Select
            value={edge.kind ?? "next"}
            onValueChange={(v) =>
              updateEdgeKind(edge.id, v as WorkflowEdge["kind"])
            }
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="next">{t("nodeInspector.edgeKindNext")}</SelectItem>
              <SelectItem value="on_error">
                {t("nodeInspector.edgeKindOnError")}
              </SelectItem>
            </SelectContent>
          </Select>
          {edge.when && (
            <span className="text-[10px] text-muted-foreground">
              when={edge.when}
            </span>
          )}
          {edge.case && (
            <span className="text-[10px] text-muted-foreground">
              case={edge.case}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
