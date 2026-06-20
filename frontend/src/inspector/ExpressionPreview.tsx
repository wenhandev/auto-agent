import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play } from "lucide-react";
import { apiClient } from "@/api-platform";
import { usePlatformStore } from "@/platformStore";
import type { ExpressionPreviewResponse } from "@/types-platform";
import { useVariablePredecessors } from "@/inspector/AvailableVariablesTab";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface Props {
  nodeId: string;
  defaultExpression?: string;
}

function formatPreviewValue(res: ExpressionPreviewResponse): string {
  if (!res.ok) return res.error ?? "error";
  if (res.value === null || res.value === undefined) return "null";
  if (typeof res.value === "string") return res.value;
  try {
    return JSON.stringify(res.value, null, 2);
  } catch {
    return String(res.value);
  }
}

export function ExpressionPreview({
  nodeId,
  defaultExpression = "",
}: Props) {
  const { t } = useTranslation();
  const workflowId = usePlatformStore((s) => s.currentWorkflowId);
  const { predecessors, shapes } = useVariablePredecessors(nodeId);
  const [expression, setExpression] = useState(defaultExpression);
  const [result, setResult] = useState<ExpressionPreviewResponse | null>(null);

  const previewContext = useMemo(() => {
    const nodes: Record<string, { output: unknown }> = {};
    for (const id of predecessors) {
      const output = shapes[id];
      if (output !== undefined) {
        nodes[id] = { output };
      }
    }
    return { nodes };
  }, [predecessors, shapes]);

  const previewMut = useMutation({
    mutationFn: () =>
      apiClient.expressions.preview({
        expression,
        workflow_id: workflowId ?? undefined,
        context: previewContext,
      }),
    onSuccess: setResult,
  });

  return (
    <div className="flex flex-col gap-2 rounded-md border bg-muted/20 p-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t("expressionPreview.title", "Expression preview")}
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="expr-preview-input" className="text-[11px]">
          {t("expressionPreview.expressionLabel", "Expression")}
        </Label>
        <Input
          id="expr-preview-input"
          value={expression}
          onChange={(e) => setExpression(e.target.value)}
          className="font-mono text-xs"
          placeholder="{{= nodes.n1.output.x + 1 }}"
        />
      </div>
      <Button
        size="sm"
        variant="outline"
        className="h-7 self-start"
        disabled={!expression.trim() || previewMut.isPending}
        onClick={() => previewMut.mutate()}
      >
        <Play className="mr-1 h-3 w-3" />
        {t("expressionPreview.run", "Preview")}
      </Button>
      {result && (
        <pre
          className={
            result.ok
              ? "max-h-32 overflow-auto rounded border bg-background px-2 py-1.5 font-mono text-[11px] text-emerald-600 dark:text-emerald-400"
              : "max-h-32 overflow-auto rounded border bg-background px-2 py-1.5 font-mono text-[11px] text-destructive"
          }
        >
          {result.ok && result.type
            ? `[${result.type}] ${formatPreviewValue(result)}`
            : formatPreviewValue(result)}
        </pre>
      )}
    </div>
  );
}
