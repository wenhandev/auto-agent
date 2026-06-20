import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { WorkflowNode } from "@/types";
import { ExpressionPreview } from "./ExpressionPreview";
import { replaceNodeParams } from "./insertFlowNode";
import { TokenTextField } from "./TokenTextField";
import { useVariablePredecessors } from "./AvailableVariablesTab";

type PredicateOp =
  | "=="
  | "!="
  | ">"
  | ">="
  | "<"
  | "<="
  | "in"
  | "not_in"
  | "is_truthy"
  | "is_falsy";

interface ConditionPredicate {
  left?: unknown;
  op?: PredicateOp;
  right?: unknown;
}

const OPS: PredicateOp[] = [
  "==",
  "!=",
  ">",
  ">=",
  "<",
  "<=",
  "in",
  "not_in",
  "is_truthy",
  "is_falsy",
];

function parsePredicate(raw: unknown): ConditionPredicate {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as ConditionPredicate;
  }
  return {};
}

interface Props {
  node: WorkflowNode;
}

export function ConditionParamsEditor({ node }: Props) {
  const { t } = useTranslation();
  const { shapes } = useVariablePredecessors(node.id);
  const predicate = parsePredicate(node.params?.predicate);
  const expr =
    typeof node.params?.expr === "string" ? node.params.expr : "";

  const [mode, setMode] = useState<"simple" | "advanced">(
    predicate.left !== undefined || predicate.op ? "simple" : "advanced",
  );

  const op = (predicate.op ?? "==") as PredicateOp;
  const unary = op === "is_truthy" || op === "is_falsy";

  function saveSimple(next: ConditionPredicate) {
    replaceNodeParams(node.id, { predicate: next });
  }

  function saveAdvanced(nextExpr: string) {
    replaceNodeParams(node.id, { expr: nextExpr });
  }

  return (
    <Tabs
      value={mode}
      onValueChange={(v) => setMode(v as "simple" | "advanced")}
      className="w-full"
    >
      <TabsList className="h-8 w-full">
        <TabsTrigger value="simple" className="flex-1 text-xs">
          {t("conditionEditor.tabSimple")}
        </TabsTrigger>
        <TabsTrigger value="advanced" className="flex-1 text-xs">
          {t("conditionEditor.tabAdvanced")}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="simple" className="mt-2 space-y-2">
        <div className="space-y-1">
          <Label className="text-[11px]">{t("conditionEditor.left")}</Label>
          <TokenTextField
            value={String(predicate.left ?? "")}
            onChange={(left) =>
              saveSimple({ ...predicate, left, op: predicate.op ?? "==" })
            }
            shapes={shapes}
            placeholder="{{nodes.http.output.status}}"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">{t("conditionEditor.operator")}</Label>
          <Select
            value={op}
            onValueChange={(value) =>
              saveSimple({ ...predicate, op: value as PredicateOp })
            }
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {OPS.map((item) => (
                <SelectItem key={item} value={item} className="text-xs">
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!unary && (
          <div className="space-y-1">
            <Label className="text-[11px]">{t("conditionEditor.right")}</Label>
            <TokenTextField
              value={String(predicate.right ?? "")}
              onChange={(right) => saveSimple({ ...predicate, right, op })}
              shapes={shapes}
              placeholder="400"
            />
          </div>
        )}
      </TabsContent>
      <TabsContent value="advanced" className="mt-2 space-y-2">
        <div className="space-y-1">
          <Label className="text-[11px]">{t("conditionEditor.expr")}</Label>
          <Textarea
            className="min-h-[72px] font-mono text-xs"
            value={expr}
            onChange={(e) => saveAdvanced(e.target.value)}
            placeholder="{{= nodes.n1.output.count > 0 }}"
          />
        </div>
        <ExpressionPreview nodeId={node.id} defaultExpression={expr} />
      </TabsContent>
    </Tabs>
  );
}
