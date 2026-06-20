import { useTranslation } from "react-i18next";
import { useStore } from "@/store";
import type { NodeRuntimeState, WorkflowNode } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { statusBadgeVariant } from "@/lib/status";
import { cn } from "@/lib/utils";

interface NodeOutput {
  node: WorkflowNode;
  state: NodeRuntimeState;
}

function pickFinalOutput(
  nodes: WorkflowNode[] | undefined,
  states: Record<string, NodeRuntimeState>,
): NodeOutput | null {
  if (!nodes) return null;
  let lastExtract: NodeOutput | null = null;
  let lastWithOutput: NodeOutput | null = null;
  for (const node of nodes) {
    const state = states[node.id];
    if (!state || state.output === undefined || state.output === null) continue;
    lastWithOutput = { node, state };
    if (node.type === "extract") lastExtract = { node, state };
  }
  return lastExtract ?? lastWithOutput;
}

function collectResultOutputs(
  nodes: WorkflowNode[] | undefined,
  states: Record<string, NodeRuntimeState>,
): NodeOutput[] {
  if (!nodes) return [];
  const primary = nodes
    .filter((n) => n.type === "extract" || n.type === "fuzzy_action")
    .map((node) => ({ node, state: states[node.id] }))
    .filter(
      (item): item is NodeOutput =>
        item.state !== undefined &&
        item.state.output !== undefined &&
        item.state.output !== null,
    );
  if (primary.length > 0) return primary;
  const fallback = pickFinalOutput(nodes, states);
  return fallback ? [fallback] : [];
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" && value !== null && !Array.isArray(value)
  );
}

function RenderOutput({ output }: { output: unknown }) {
  const { t } = useTranslation();
  if (typeof output === "string") {
    return (
      <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
        {output}
      </div>
    );
  }
  if (isPlainObject(output) && typeof output.text === "string") {
    const text = output.text as string;
    const meta: Array<[string, string]> = [];
    if (typeof output.page_url === "string")
      meta.push([t("result.metaUrl"), output.page_url]);
    if (typeof output.page_title === "string")
      meta.push([t("result.metaPage"), output.page_title]);
    if (typeof output.instruction === "string")
      meta.push([t("result.metaInstruction"), output.instruction]);
    return (
      <div className="space-y-2">
        <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          {text}
        </div>
        {meta.length > 0 && (
          <dl className="grid gap-1 text-[11px]">
            {meta.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <dt className="font-semibold text-muted-foreground">{k}</dt>
                <dd className="break-all text-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    );
  }
  if (isPlainObject(output) && typeof output.summary === "string") {
    return (
      <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
        {output.summary}
      </div>
    );
  }
  return (
    <pre className="overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-[11px] text-foreground">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}

function OutputSection({ item }: { item: NodeOutput }) {
  const errorText =
    isPlainObject(item.state.output) &&
    typeof item.state.output.error === "string"
      ? item.state.output.error
      : null;

  return (
    <div className={cn("space-y-2", errorText && "rounded-md border border-destructive/40 p-2")}>
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="font-mono text-[10px]">
          {item.node.type}
        </Badge>
        <span className="truncate text-[11px] text-muted-foreground">
          {item.node.label}
        </span>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {item.node.id}
        </span>
      </div>
      <RenderOutput output={item.state.output} />
      {errorText && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
          {errorText}
        </div>
      )}
    </div>
  );
}

export function ResultPanel() {
  const { t } = useTranslation();
  const runStatus = useStore((s) => s.runStatus);
  const workflow = useStore((s) => s.workflow);
  const nodeStates = useStore((s) => s.nodeStates);

  if (runStatus !== "completed" && runStatus !== "failed") return null;

  const outputs = collectResultOutputs(workflow?.nodes, nodeStates);

  if (!outputs.length) {
    return (
      <div className="border-b bg-muted/20">
        <div className="flex items-center justify-between px-4 py-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {t("result.title")}
          </span>
          <Badge variant={statusBadgeVariant(runStatus)}>
            {t(`status.${runStatus}`, runStatus)}
          </Badge>
        </div>
        <div className="px-4 pb-3 text-xs text-muted-foreground">
          {t("result.empty")}
        </div>
      </div>
    );
  }

  return (
    <div className="border-b bg-muted/20">
      <div className="flex items-center justify-between px-4 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t("result.title")}
          {outputs.length > 1 && (
            <span className="ml-1.5 font-normal normal-case text-muted-foreground">
              ({outputs.length})
            </span>
          )}
        </span>
        <Badge variant={statusBadgeVariant(runStatus)}>
          {t(`status.${runStatus}`, runStatus)}
        </Badge>
      </div>
      <div className="max-h-64 space-y-3 overflow-y-auto px-4 py-3">
        {outputs.map((item, i) => (
          <div key={item.node.id}>
            {i > 0 && <Separator className="mb-3" />}
            <OutputSection item={item} />
          </div>
        ))}
      </div>
    </div>
  );
}
