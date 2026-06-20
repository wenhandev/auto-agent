import { useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { IntegrationAppLabel } from "@/components/IntegrationAppLabel";
import { apiClient } from "@/api-platform";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { IntegrationFieldSpec, IntegrationOperationSpec } from "@/types-platform";
import type { WorkflowNode } from "@/types";
import { useVariablePredecessors } from "./AvailableVariablesTab";
import {
  coerceStringParam,
  stringifyParamValue,
  TokenTextField,
} from "./TokenTextField";
import { updateNodeParams } from "./updateNodeParams";
import { VariableInsertMenu } from "./VariableTree";

interface Props {
  node: WorkflowNode;
}

function IntegrationFieldRow({
  node,
  field,
  value,
  shapes,
  predecessorTrees,
}: {
  node: WorkflowNode;
  field: IntegrationFieldSpec;
  value: unknown;
  shapes: Record<string, unknown>;
  predecessorTrees: ReturnType<typeof useVariablePredecessors>["predecessorTrees"];
}) {
  const insertRef = useRef<((token: string) => void) | null>(null);
  const strValue = stringifyParamValue(value);

  const setField = (next: unknown) => {
    const fields = { ...(node.params?.fields as Record<string, unknown> | undefined) };
    fields[field.name] = next;
    updateNodeParams(node.id, { fields });
  };

  if (field.kind === "boolean") {
    return (
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">{field.label || field.name}</Label>
        <Switch
          checked={Boolean(value)}
          onCheckedChange={(checked) => setField(checked)}
        />
      </div>
    );
  }

  if (field.kind === "options" && field.options?.length) {
    return (
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{field.label || field.name}</Label>
        <Select
          value={strValue || String(field.default ?? "")}
          onValueChange={(v) => setField(v)}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {field.options.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label || opt.value}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">{field.label || field.name}</Label>
        <VariableInsertMenu
          predecessors={predecessorTrees}
          onInsert={(token) => insertRef.current?.(token)}
        />
      </div>
      {field.kind === "number" ? (
        <Input
          type="number"
          className="h-8 text-xs"
          value={strValue}
          onChange={(e) =>
            setField(
              e.target.value === "" ? "" : Number(e.target.value),
            )
          }
        />
      ) : (
        <TokenTextField
          value={strValue}
          onChange={(next) =>
            setField(coerceStringParam(next, "string"))
          }
          shapes={shapes}
          insertTokenRef={insertRef}
        />
      )}
    </div>
  );
}

export function IntegrationParamsEditor({ node }: Props) {
  const { t } = useTranslation();
  const app = String(node.params?.app ?? "");
  const resource = String(node.params?.resource ?? "");
  const operation = String(node.params?.operation ?? "");
  const fields = (node.params?.fields as Record<string, unknown>) ?? {};
  const { predecessorTrees, shapes } = useVariablePredecessors(node.id);

  const catalogueQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: () => apiClient.integrations.list(),
  });

  const descriptorQuery = useQuery({
    queryKey: ["integrations", app],
    queryFn: () => apiClient.integrations.get(app),
    enabled: !!app,
  });

  const descriptor = descriptorQuery.data;
  const apps = catalogueQuery.data ?? [];

  const resources = descriptor?.resources ?? [];
  const selectedResource = resources.find((r) => r.name === resource);
  const operations: IntegrationOperationSpec[] =
    selectedResource?.operations ?? [];
  const selectedOp = operations.find((o) => o.name === operation);

  const appOptions = useMemo(
    () => apps.map((d) => d.app).sort(),
    [apps],
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <Label className="text-[10px] uppercase text-muted-foreground">
          {t("nodeInspector.integrationApp")}
        </Label>
        <Select
          value={app || "__none__"}
          onValueChange={(v) =>
            updateNodeParams(node.id, {
              app: v === "__none__" ? "" : v,
              resource: "",
              operation: "",
              fields: {},
            })
          }
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder={t("nodeInspector.integrationSelectApp")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">—</SelectItem>
            {appOptions.map((name) => (
              <SelectItem key={name} value={name}>
                <IntegrationAppLabel app={name} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {app && descriptor && (
        <div className="flex flex-col gap-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            {t("nodeInspector.integrationResource")}
          </Label>
          <Select
            value={resource || "__none__"}
            onValueChange={(v) =>
              updateNodeParams(node.id, {
                resource: v === "__none__" ? "" : v,
                operation: "",
                fields: {},
              })
            }
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">—</SelectItem>
              {resources.map((r) => (
                <SelectItem key={r.name} value={r.name}>
                  {r.label || r.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {operations.length > 0 && (
        <div className="flex flex-col gap-1">
          <Label className="text-[10px] uppercase text-muted-foreground">
            {t("nodeInspector.integrationOperation")}
          </Label>
          <Select
            value={operation || "__none__"}
            onValueChange={(v) => {
              const op = operations.find((o) => o.name === v);
              const defaults: Record<string, unknown> = {};
              for (const f of op?.fields ?? []) {
                if (f.default !== undefined) {
                  defaults[f.name] = f.default;
                }
              }
              updateNodeParams(node.id, {
                operation: v === "__none__" ? "" : v,
                fields: defaults,
              });
            }}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">—</SelectItem>
              {operations.map((o) => (
                <SelectItem key={o.name} value={o.name}>
                  {o.label || o.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {selectedOp && (
        <div className="flex flex-col gap-2 border-t pt-2">
          {selectedOp.fields.map((field) => (
            <IntegrationFieldRow
              key={field.name}
              node={node}
              field={field}
              value={fields[field.name] ?? field.default ?? ""}
              shapes={shapes}
              predecessorTrees={predecessorTrees}
            />
          ))}
        </div>
      )}

      <div className="flex flex-col gap-1">
        <Label className="text-[10px] uppercase text-muted-foreground">
          {t("nodeInspector.integrationCredential")}
        </Label>
        <Input
          className="h-8 font-mono text-xs"
          placeholder="{{cred.name}}"
          value={stringifyParamValue(node.params?.credential)}
          onChange={(e) =>
            updateNodeParams(node.id, { credential: e.target.value || null })
          }
        />
      </div>
    </div>
  );
}
