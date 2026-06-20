import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useStore } from "@/store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { statusBadgeVariant } from "@/lib/status";
import { AvailableVariablesTab } from "@/inspector/AvailableVariablesTab";
import { ExpressionPreview } from "@/inspector/ExpressionPreview";
import { NodeErrorHandlingSection } from "@/inspector/NodeErrorHandlingSection";
import { NodeParamsEditor } from "@/inspector/NodeParamsEditor";
import { OutgoingEdgesSection } from "@/inspector/OutgoingEdgesSection";

function formatOutput(output: unknown): string {
  if (output === null || output === undefined) return "";
  if (typeof output === "string") return output;
  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
}

export function NodeInspector() {
  const { t } = useTranslation();
  const selectedId = useStore((s) => s.selectedNodeId);
  const workflow = useStore((s) => s.workflow);
  const states = useStore((s) => s.nodeStates);
  const selectNode = useStore((s) => s.selectNode);

  if (!selectedId) return null;
  const node = workflow?.nodes.find((n) => n.id === selectedId);
  if (!node) return null;
  const state = states[selectedId];
  const output = state?.output;
  const formatted = formatOutput(output);
  const status = state?.status ?? "idle";

  return (
    <div className="absolute right-4 top-4 z-30 flex w-[360px] max-h-[80%] flex-col overflow-hidden rounded-lg border bg-card shadow-lg">
      <div className="flex items-start gap-2 border-b px-3 py-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="font-mono text-[10px]">
              {node.type}
            </Badge>
            <span className="truncate text-sm font-semibold text-foreground">
              {node.label}
            </span>
          </div>
          <span className="truncate font-mono text-[10px] text-muted-foreground">
            {node.id}
          </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => selectNode(null)}
          aria-label={t("nodeInspector.closeAria")}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex items-center gap-2 px-3 py-2">
        <Badge variant={statusBadgeVariant(status)}>
          {t(`status.${status}`, status)}
        </Badge>
        {state?.error && (
          <span className="truncate text-xs text-destructive">
            {state.error}
          </span>
        )}
      </div>
      <Separator />
      <Tabs defaultValue="properties" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="mx-3 mt-2 h-8 w-auto justify-start">
          <TabsTrigger value="properties" className="text-xs">
            {t("nodeInspector.tabProperties")}
          </TabsTrigger>
          <TabsTrigger value="variables" className="text-xs">
            {t("nodeInspector.tabVariables")}
          </TabsTrigger>
        </TabsList>
        <TabsContent
          value="properties"
          className="mt-0 flex-1 overflow-auto px-3 pb-3 data-[state=inactive]:hidden"
        >
          <div className="flex flex-col gap-3 pt-2">
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {t("nodeInspector.paramsTitle")}
              </div>
              <NodeParamsEditor node={node} />
            </div>
            {node.type !== "start" && node.type !== "end" && (
              <>
                <NodeErrorHandlingSection node={node} />
                <OutgoingEdgesSection nodeId={node.id} />
              </>
            )}
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {t("nodeInspector.outputTitle")}
              </div>
              {formatted ? (
                <pre className="max-h-48 overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-[11px] text-foreground">
                  {formatted}
                </pre>
              ) : (
                <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                  {t("nodeInspector.noOutput")}
                </div>
              )}
            </div>
          </div>
        </TabsContent>
        <TabsContent
          value="variables"
          className="mt-0 flex-1 overflow-auto px-3 pb-3 data-[state=inactive]:hidden"
        >
          <div className="flex flex-col gap-3 pt-2">
            <AvailableVariablesTab nodeId={node.id} />
            <ExpressionPreview nodeId={node.id} />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
