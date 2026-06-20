import { useTranslation } from "react-i18next";
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
import type { WorkflowNode } from "@/types";
import { updateNodeOnError, updateNodeRetry } from "./updateNodeMeta";

interface Props {
  node: WorkflowNode;
}

export function NodeErrorHandlingSection({ node }: Props) {
  const { t } = useTranslation();
  const retryEnabled = node.retry != null;
  const maxAttempts = node.retry?.max_attempts ?? 3;
  const backoffMs = node.retry?.backoff_ms ?? 1000;
  const onError = node.on_error ?? "fail_run";

  return (
    <div className="flex flex-col gap-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t("nodeInspector.errorHandlingTitle")}
      </div>

      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={`retry-${node.id}`} className="text-xs">
          {t("nodeInspector.retryEnabled")}
        </Label>
        <Switch
          id={`retry-${node.id}`}
          checked={retryEnabled}
          onCheckedChange={(checked) =>
            updateNodeRetry(
              node.id,
              checked ? { max_attempts: maxAttempts, backoff_ms: backoffMs } : null,
            )
          }
        />
      </div>

      {retryEnabled && (
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-1">
            <Label className="text-[10px] uppercase text-muted-foreground">
              {t("nodeInspector.retryMaxAttempts")}
            </Label>
            <Input
              type="number"
              min={1}
              max={10}
              className="h-8 text-xs"
              value={maxAttempts}
              onChange={(e) =>
                updateNodeRetry(node.id, {
                  max_attempts: Math.max(1, Number(e.target.value) || 1),
                  backoff_ms: backoffMs,
                })
              }
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-[10px] uppercase text-muted-foreground">
              {t("nodeInspector.retryBackoffMs")}
            </Label>
            <Input
              type="number"
              min={0}
              step={100}
              className="h-8 text-xs"
              value={backoffMs}
              onChange={(e) =>
                updateNodeRetry(node.id, {
                  max_attempts: maxAttempts,
                  backoff_ms: Math.max(0, Number(e.target.value) || 0),
                })
              }
            />
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <Label className="text-[10px] uppercase text-muted-foreground">
          {t("nodeInspector.onErrorPolicy")}
        </Label>
        <Select
          value={onError}
          onValueChange={(v) =>
            updateNodeOnError(
              node.id,
              v as WorkflowNode["on_error"],
            )
          }
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="fail_run">
              {t("nodeInspector.onErrorFailRun")}
            </SelectItem>
            <SelectItem value="continue">
              {t("nodeInspector.onErrorContinue")}
            </SelectItem>
            <SelectItem value="branch">
              {t("nodeInspector.onErrorBranch")}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
