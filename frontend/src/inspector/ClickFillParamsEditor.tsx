import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Crosshair } from "lucide-react";
import type { WorkflowNode } from "@/types";
import { useStore } from "@/store";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useVariablePredecessors } from "./AvailableVariablesTab";
import { ElementPickerDialog } from "./ElementPickerDialog";
import {
  coerceStringParam,
  stringifyParamValue,
  TokenTextField,
} from "./TokenTextField";
import { updateNodeParams } from "./updateNodeParams";
import { VariableInsertMenu } from "./VariableTree";
import { getPredecessorIds } from "./variableUtils";

function findUpstreamNavigateUrl(nodeId: string): string {
  const workflow = useStore.getState().workflow;
  if (!workflow) return "";
  const preds = getPredecessorIds(nodeId, workflow.edges);
  const nodesById = new Map(workflow.nodes.map((n) => [n.id, n]));
  for (const pid of preds) {
    const n = nodesById.get(pid);
    if (n?.type === "navigate" && n.params?.url) {
      return stringifyParamValue(n.params.url);
    }
  }
  return "";
}

export function ClickFillParamsEditor({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = useState(false);
  const { predecessorTrees, shapes } = useVariablePredecessors(node.id);
  const defaultUrl = useMemo(() => findUpstreamNavigateUrl(node.id), [node.id]);

  const selectorRaw = node.params?.selector;
  const selectorValue = stringifyParamValue(selectorRaw);
  const valueRaw = node.params?.value;
  const valueStr = stringifyParamValue(valueRaw);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {t("nodeInspector.fields.selector")}
          </Label>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 gap-1 px-2 text-[10px]"
              onClick={() => setPickerOpen(true)}
            >
              <Crosshair className="h-3 w-3" />
              {t("elementPicker.pickButton")}
            </Button>
            <VariableInsertMenu
              predecessors={predecessorTrees}
              onInsert={(token) =>
                updateNodeParams(node.id, {
                  selector: coerceStringParam(`${selectorValue}${token}`, "string"),
                })
              }
            />
          </div>
        </div>
        <TokenTextField
          value={selectorValue}
          onChange={(next) =>
            updateNodeParams(node.id, {
              selector: coerceStringParam(next, "string"),
            })
          }
          shapes={shapes}
        />
      </div>

      {node.type === "fill" && (
        <div className="flex flex-col gap-1">
          <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {t("nodeInspector.fields.value")}
          </Label>
          <TokenTextField
            value={valueStr}
            onChange={(next) =>
              updateNodeParams(node.id, {
                value: coerceStringParam(next, "string"),
              })
            }
            shapes={shapes}
          />
        </div>
      )}

      <ElementPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        defaultUrl={defaultUrl}
        onApply={(selector) =>
          updateNodeParams(node.id, { selector: coerceStringParam(selector, "string") })
        }
      />
    </div>
  );
}
