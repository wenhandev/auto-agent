import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { NodeType, WorkflowNode } from "@/types";
import { useVariablePredecessors } from "./AvailableVariablesTab";
import { IntegrationParamsEditor } from "./IntegrationParamsEditor";
import {
  coerceStringParam,
  stringifyParamValue,
  TokenTextField,
} from "./TokenTextField";
import { updateNodeParams } from "./updateNodeParams";
import { VariableInsertMenu } from "./VariableTree";
import { ClickFillParamsEditor } from "./ClickFillParamsEditor";
import { ConditionParamsEditor } from "./ConditionParamsEditor";

type ParamField = {
  key: string;
  labelKey: string;
  kind: "string" | "number";
  multiline?: boolean;
};

const PARAM_FIELDS: Partial<Record<NodeType, ParamField[]>> = {
  navigate: [{ key: "url", labelKey: "url", kind: "string" }],
  click: [{ key: "selector", labelKey: "selector", kind: "string" }],
  fill: [
    { key: "selector", labelKey: "selector", kind: "string" },
    { key: "value", labelKey: "value", kind: "string" },
  ],
  extract: [
    {
      key: "instruction",
      labelKey: "instruction",
      kind: "string",
      multiline: true,
    },
  ],
  wait: [{ key: "ms", labelKey: "ms", kind: "number" }],
  fuzzy_action: [
    { key: "action", labelKey: "action", kind: "string" },
    {
      key: "instruction",
      labelKey: "instruction",
      kind: "string",
      multiline: true,
    },
  ],
  condition: [],
  filter: [
    { key: "predicate", labelKey: "predicate", kind: "string", multiline: true },
  ],
  split_out: [
    { key: "field", labelKey: "field", kind: "string" },
    { key: "out_field", labelKey: "outField", kind: "string" },
  ],
  datetime: [
    { key: "field", labelKey: "field", kind: "string" },
    { key: "output_field", labelKey: "outputField", kind: "string" },
    { key: "format", labelKey: "format", kind: "string" },
  ],
  approval: [
    { key: "prompt", labelKey: "prompt", kind: "string", multiline: true },
  ],
  limit: [{ key: "count", labelKey: "count", kind: "number" }],
  aggregate: [
    { key: "field", labelKey: "field", kind: "string" },
    { key: "out_field", labelKey: "outField", kind: "string" },
    { key: "key", labelKey: "keyField", kind: "string" },
  ],
  remove_duplicates: [
    { key: "fields", labelKey: "fieldsList", kind: "string" },
  ],
};

interface NodeParamsEditorProps {
  node: WorkflowNode;
}

function ParamFieldRow({
  node,
  field,
  shapes,
  predecessorTrees,
}: {
  node: WorkflowNode;
  field: ParamField;
  shapes: Record<string, unknown>;
  predecessorTrees: ReturnType<typeof useVariablePredecessors>["predecessorTrees"];
}) {
  const { t } = useTranslation();
  const insertRef = useRef<((token: string) => void) | null>(null);
  const raw = node.params?.[field.key];
  const value = stringifyParamValue(raw);

  const setValue = (next: string) => {
    updateNodeParams(node.id, {
      [field.key]: coerceStringParam(next, field.kind),
    });
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {t(`nodeInspector.fields.${field.labelKey}`, field.key)}
        </Label>
        <VariableInsertMenu
          predecessors={predecessorTrees}
          onInsert={(token) => insertRef.current?.(token)}
        />
      </div>
      <TokenTextField
        value={value}
        onChange={setValue}
        shapes={shapes}
        multiline={field.multiline}
        insertTokenRef={insertRef}
      />
    </div>
  );
}

function JsonParamEditor({
  node,
  paramKey,
  labelKey,
}: {
  node: WorkflowNode;
  paramKey: string;
  labelKey: string;
}) {
  const { t } = useTranslation();
  const raw = node.params?.[paramKey];
  const text =
    typeof raw === "string"
      ? raw
      : JSON.stringify(raw ?? (paramKey === "assignments" ? [] : []), null, 2);

  return (
    <div className="flex flex-col gap-1">
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {t(`nodeInspector.fields.${labelKey}`, paramKey)}
      </Label>
      <Textarea
        className="font-mono text-[11px]"
        rows={5}
        value={text}
        onChange={(e) => {
          try {
            updateNodeParams(node.id, {
              [paramKey]: JSON.parse(e.target.value),
            });
          } catch {
            updateNodeParams(node.id, { [paramKey]: e.target.value });
          }
        }}
      />
    </div>
  );
}

function SetNodeEditor({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const keepOnly = Boolean(node.params?.keep_only_set);
  const includeBinary = node.params?.include_binary !== false;

  return (
    <div className="flex flex-col gap-3">
      <JsonParamEditor node={node} paramKey="assignments" labelKey="assignments" />
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">{t("nodeInspector.fields.keepOnlySet")}</Label>
        <Switch
          checked={keepOnly}
          onCheckedChange={(checked) =>
            updateNodeParams(node.id, { keep_only_set: checked })
          }
        />
      </div>
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">{t("nodeInspector.fields.includeBinary")}</Label>
        <Switch
          checked={includeBinary}
          onCheckedChange={(checked) =>
            updateNodeParams(node.id, { include_binary: checked })
          }
        />
      </div>
      <JsonParamEditor
        node={node}
        paramKey="fields_to_remove"
        labelKey="fieldsToRemove"
      />
    </div>
  );
}

function SortNodeEditor({ node }: { node: WorkflowNode }) {
  return <JsonParamEditor node={node} paramKey="keys" labelKey="sortKeys" />;
}

function LimitNodeEditor({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const keep = String(node.params?.keep ?? "first");
  const { predecessorTrees, shapes } = useVariablePredecessors(node.id);
  const countField: ParamField = { key: "count", labelKey: "count", kind: "number" };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <Label className="text-[10px] uppercase text-muted-foreground">
          {t("nodeInspector.fields.keep")}
        </Label>
        <Select
          value={keep}
          onValueChange={(v) => updateNodeParams(node.id, { keep: v })}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="first">{t("nodeInspector.fields.keepFirst")}</SelectItem>
            <SelectItem value="last">{t("nodeInspector.fields.keepLast")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <ParamFieldRow
        node={node}
        field={countField}
        shapes={shapes}
        predecessorTrees={predecessorTrees}
      />
    </div>
  );
}

function AggregateNodeEditor({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const operation = String(node.params?.operation ?? "count");
  const fields = PARAM_FIELDS.aggregate ?? [];
  const { predecessorTrees, shapes } = useVariablePredecessors(node.id);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <Label className="text-[10px] uppercase text-muted-foreground">
          {t("nodeInspector.fields.operation")}
        </Label>
        <Select
          value={operation}
          onValueChange={(v) => updateNodeParams(node.id, { operation: v })}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {["count", "sum", "avg", "min", "max", "concat", "group_by"].map(
              (op) => (
                <SelectItem key={op} value={op}>
                  {op}
                </SelectItem>
              ),
            )}
          </SelectContent>
        </Select>
      </div>
      {fields.map((field) => (
        <ParamFieldRow
          key={field.key}
          node={node}
          field={field}
          shapes={shapes}
          predecessorTrees={predecessorTrees}
        />
      ))}
    </div>
  );
}

function RemoveDuplicatesEditor({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const compare = String(node.params?.compare ?? "selected_fields");
  const fields = PARAM_FIELDS.remove_duplicates ?? [];
  const { predecessorTrees, shapes } = useVariablePredecessors(node.id);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <Label className="text-[10px] uppercase text-muted-foreground">
          {t("nodeInspector.fields.compareMode")}
        </Label>
        <Select
          value={compare}
          onValueChange={(v) => updateNodeParams(node.id, { compare: v })}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="selected_fields">
              {t("nodeInspector.fields.compareSelected")}
            </SelectItem>
            <SelectItem value="all_fields">
              {t("nodeInspector.fields.compareAll")}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
      {compare === "selected_fields" &&
        fields.map((field) => {
          const raw = node.params?.fields;
          const comma =
            Array.isArray(raw) ? raw.join(", ") : stringifyParamValue(raw);
          return (
            <div key={field.key} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <Label className="text-[10px] uppercase text-muted-foreground">
                  {t(`nodeInspector.fields.${field.labelKey}`)}
                </Label>
                <VariableInsertMenu
                  predecessors={predecessorTrees}
                  onInsert={() => {}}
                />
              </div>
              <TokenTextField
                value={comma}
                onChange={(next) =>
                  updateNodeParams(node.id, {
                    fields: next
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
                shapes={shapes}
              />
            </div>
          );
        })}
    </div>
  );
}

function RenameKeysEditor({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const errorOnCollision = Boolean(node.params?.error_on_collision);

  return (
    <div className="flex flex-col gap-3">
      <JsonParamEditor node={node} paramKey="pairs" labelKey="renamePairs" />
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">{t("nodeInspector.fields.errorOnCollision")}</Label>
        <Switch
          checked={errorOnCollision}
          onCheckedChange={(checked) =>
            updateNodeParams(node.id, { error_on_collision: checked })
          }
        />
      </div>
    </div>
  );
}

function ApprovalInputsEditor({ node }: { node: WorkflowNode }) {
  return <JsonParamEditor node={node} paramKey="inputs" labelKey="approvalInputs" />;
}

export function NodeParamsEditor({ node }: NodeParamsEditorProps) {
  const { t } = useTranslation();

  if (node.type === "integration") {
    return <IntegrationParamsEditor node={node} />;
  }

  if (node.type === "set") {
    return <SetNodeEditor node={node} />;
  }
  if (node.type === "sort") {
    return <SortNodeEditor node={node} />;
  }
  if (node.type === "limit") {
    return <LimitNodeEditor node={node} />;
  }
  if (node.type === "aggregate") {
    return <AggregateNodeEditor node={node} />;
  }
  if (node.type === "remove_duplicates") {
    return <RemoveDuplicatesEditor node={node} />;
  }
  if (node.type === "rename_keys") {
    return <RenameKeysEditor node={node} />;
  }
  if (node.type === "click" || node.type === "fill") {
    return <ClickFillParamsEditor node={node} />;
  }
  if (node.type === "condition") {
    return <ConditionParamsEditor node={node} />;
  }

  const fields = PARAM_FIELDS[node.type];
  const { predecessorTrees, shapes } = useVariablePredecessors(node.id);

  if (!fields?.length) {
    return (
      <pre className="max-h-48 overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-[11px] text-foreground">
        {JSON.stringify(node.params ?? {}, null, 2)}
      </pre>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {fields.map((field) => (
        <ParamFieldRow
          key={field.key}
          node={node}
          field={field}
          shapes={shapes}
          predecessorTrees={predecessorTrees}
        />
      ))}
      {node.type === "approval" && <ApprovalInputsEditor node={node} />}
      {fields.length < Object.keys(node.params ?? {}).length && (
        <div className="text-[10px] text-muted-foreground">
          {t("nodeInspector.extraParamsHint")}
        </div>
      )}
    </div>
  );
}
