import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useStore } from "@/store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { statusBadgeVariant } from "@/lib/status";

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
    <div className="absolute right-4 top-4 z-30 flex w-[340px] max-h-[80%] flex-col overflow-hidden rounded-lg border bg-card shadow-lg">
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
      <div className="flex flex-col gap-2 overflow-auto p-3">
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t("nodeInspector.paramsTitle")}
          </div>
          <pre className="max-h-32 overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-[11px] text-foreground">
            {JSON.stringify(node.params ?? {}, null, 2)}
          </pre>
        </div>
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t("nodeInspector.outputTitle")}
          </div>
          {formatted ? (
            <pre className="max-h-64 overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-[11px] text-foreground">
              {formatted}
            </pre>
          ) : (
            <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
              {t("nodeInspector.noOutput")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
