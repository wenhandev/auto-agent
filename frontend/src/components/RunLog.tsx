import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "@/store";
import type { ItemsPreview, RunEvent } from "@/types";
import { pickRunEventField } from "@/lib/runEventNormalize";
import { cn } from "@/lib/utils";
import { ResultPanel } from "./ResultPanel";
import { Badge } from "@/components/ui/badge";

const OUTPUT_PREVIEW_LIMIT = 200;

function formatTs(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

function stringifyOutput(output: unknown): string {
  if (output === null || output === undefined) return "";
  if (typeof output === "string") return output;
  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return text.slice(0, limit - 1) + "\u2026";
}

function pickPayloadField(
  ev: RunEvent,
  key: string,
): unknown {
  return pickRunEventField(ev, key);
}

function formatEventLabel(ev: RunEvent, t: ReturnType<typeof useTranslation>["t"]): string {
  const node = ev.node_id ?? "";
  switch (ev.event) {
    case "node_retry":
      return t("runLog.events.nodeRetry", {
        node,
        attempt: String(ev.attempt ?? pickPayloadField(ev, "attempt") ?? "?"),
      });
    case "node_awaiting_approval":
      return t("runLog.events.awaitingApproval", { node });
    case "node_approved":
      return t("runLog.events.approved", { node });
    case "node_rejected":
      return t("runLog.events.rejected", { node });
    case "node_self_healed":
      return t("runLog.events.selfHealed", { node });
    case "node_self_heal_failed":
      return t("runLog.events.selfHealFailed", { node });
    case "cache_hit":
      return t("runLog.events.cacheHit", { node });
    case "cache_miss":
      return t("runLog.events.cacheMiss", { node });
    case "run_completed_with_errors":
      return t("runLog.events.completedWithErrors", {
        count: String(
          ev.failed_node_count ??
            pickPayloadField(ev, "failed_node_count") ??
            "?",
        ),
      });
    case "run_rejected":
      return t("runLog.events.runRejected");
    case "branch_pruned":
      return t("runLog.events.branchPruned", {
        edge: String(ev.edge_id ?? pickPayloadField(ev, "edge_id") ?? "?"),
      });
    case "node_skipped":
      return t("runLog.events.nodeSkipped", { node });
    case "merge_waiting":
      return t("runLog.events.mergeWaiting", {
        node,
        arrived: String(ev.arrived ?? pickPayloadField(ev, "arrived") ?? "?"),
        expected: String(ev.expected ?? pickPayloadField(ev, "expected") ?? "?"),
      });
    default:
      return ev.event;
  }
}

function formatLine(
  ev: RunEvent,
  t: ReturnType<typeof useTranslation>["t"],
): string {
  const label = formatEventLabel(ev, t);
  const parts: string[] = [`[${formatTs(ev.ts)}]`, label];
  const detail = formatEventDetail(ev);
  if (detail) parts.push(detail);
  return parts.join(" ");
}

function formatEventDetail(ev: RunEvent): string | null {
  switch (ev.event) {
    case "node_retry": {
      const err =
        ev.error ??
        (typeof pickPayloadField(ev, "error") === "string"
          ? (pickPayloadField(ev, "error") as string)
          : undefined);
      const kind =
        ev.error_kind ??
        (typeof pickPayloadField(ev, "error_kind") === "string"
          ? (pickPayloadField(ev, "error_kind") as string)
          : undefined);
      if (err && kind) return `${kind}: ${err}`;
      return err ?? null;
    }
    case "node_awaiting_approval":
      return (
        ev.prompt ??
        (typeof pickPayloadField(ev, "prompt") === "string"
          ? (pickPayloadField(ev, "prompt") as string)
          : null)
      );
    case "node_approved":
    case "node_rejected": {
      const decision =
        ev.decision ??
        (typeof pickPayloadField(ev, "decision") === "string"
          ? (pickPayloadField(ev, "decision") as string)
          : undefined);
      return decision ? `decision=${decision}` : null;
    }
    case "node_self_healed": {
      const oldSel =
        ev.original_selector ??
        (typeof pickPayloadField(ev, "original_selector") === "string"
          ? (pickPayloadField(ev, "original_selector") as string)
          : undefined);
      const newSel =
        ev.new_selector ??
        (typeof pickPayloadField(ev, "new_selector") === "string"
          ? (pickPayloadField(ev, "new_selector") as string)
          : pickPayloadField(ev, "new_selector"));
      const mode =
        ev.mode ??
        (typeof pickPayloadField(ev, "mode") === "string"
          ? (pickPayloadField(ev, "mode") as string)
          : undefined);
      const parts = [
        oldSel ? `old=${oldSel}` : null,
        newSel ? `new=${newSel}` : null,
        mode ? `mode=${mode}` : null,
      ].filter(Boolean);
      return parts.length ? parts.join(" · ") : null;
    }
    case "node_self_heal_failed": {
      const reason =
        ev.reason ??
        (typeof pickPayloadField(ev, "reason") === "string"
          ? (pickPayloadField(ev, "reason") as string)
          : undefined);
      return reason ?? ev.error ?? null;
    }
    case "cache_hit": {
      const selector =
        ev.selector ??
        (typeof pickPayloadField(ev, "selector") === "string"
          ? (pickPayloadField(ev, "selector") as string)
          : undefined);
      return selector ? `selector=${selector}` : null;
    }
    case "cache_miss": {
      const reason =
        ev.reason ??
        (typeof pickPayloadField(ev, "reason") === "string"
          ? (pickPayloadField(ev, "reason") as string)
          : undefined);
      return reason ? `reason=${reason}` : null;
    }
    case "run_completed_with_errors": {
      const ids =
        ev.failed_node_ids ??
        (Array.isArray(pickPayloadField(ev, "failed_node_ids"))
          ? (pickPayloadField(ev, "failed_node_ids") as string[])
          : undefined);
      return ids?.length ? `nodes=${ids.join(", ")}` : null;
    }
    case "branch_pruned": {
      const edgeId =
        ev.edge_id ??
        (typeof pickPayloadField(ev, "edge_id") === "string"
          ? (pickPayloadField(ev, "edge_id") as string)
          : undefined);
      return edgeId ? `edge=${edgeId}` : null;
    }
    default:
      return ev.message ?? ev.error ?? null;
  }
}

function isNestedEvent(ev: RunEvent): boolean {
  return ev.event === "node_retry";
}

function previewFromEvent(ev: RunEvent): unknown {
  const preview = (ev.items_preview ??
    pickPayloadField(ev, "items_preview")) as ItemsPreview | undefined;
  if (preview?.json && Object.keys(preview.json).length > 0) {
    return preview.json;
  }
  return ev.output;
}

function itemsCountFromEvent(ev: RunEvent): number | undefined {
  const count = ev.items_count ?? pickPayloadField(ev, "items_count");
  return typeof count === "number" ? count : undefined;
}

interface OutputBlockProps {
  output: unknown;
  itemsCount?: number;
}

function OutputBlock({ output, itemsCount }: OutputBlockProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const full = stringifyOutput(output);
  if (!full) return null;
  const isLong = full.length > OUTPUT_PREVIEW_LIMIT;
  const shown =
    expanded || !isLong ? full : truncate(full, OUTPUT_PREVIEW_LIMIT);

  return (
    <div
      className="mt-1 flex flex-col gap-1"
      title={isLong ? t("runLog.toggleHint") : undefined}
    >
      {itemsCount !== undefined && (
        <Badge variant="secondary" className="w-fit font-mono text-[10px]">
          {t("runLog.itemsCount", { count: itemsCount })}
        </Badge>
      )}
      <pre
        className={cn(
          "max-h-48 overflow-auto rounded-md border bg-muted/40 px-2 py-1.5 font-mono text-[11px] text-foreground",
          isLong && "cursor-pointer",
        )}
        onClick={isLong ? () => setExpanded((v) => !v) : undefined}
      >
        {shown}
      </pre>
      {isLong && (
        <button
          className="self-start text-[10px] font-medium text-primary hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? t("runLog.collapse") : t("runLog.expand")}
        </button>
      )}
    </div>
  );
}

const eventClasses: Record<string, string> = {
  run_started: "text-muted-foreground",
  node_started: "text-sky-400",
  node_progress: "text-sky-300",
  node_completed: "text-emerald-400",
  node_failed: "text-destructive",
  node_retry: "text-amber-400",
  node_awaiting_approval: "text-violet-400",
  node_approved: "text-emerald-400",
  node_rejected: "text-orange-400",
  node_self_healed: "text-cyan-400",
  node_self_heal_failed: "text-amber-500",
  cache_hit: "text-teal-400",
  cache_miss: "text-muted-foreground",
  run_completed: "text-emerald-400",
  run_completed_with_errors: "text-amber-400",
  run_failed: "text-destructive",
  run_aborted: "text-orange-400",
  run_rejected: "text-orange-400",
  branch_pruned: "text-muted-foreground/70",
  node_skipped: "text-muted-foreground/70",
  merge_waiting: "text-amber-400/80",
};

export function RunLog() {
  const { t } = useTranslation();
  const logs = useStore((s) => s.logs);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t("runLog.title")}
      </div>
      <ResultPanel />
      <div
        ref={bodyRef}
        className="scrollbar-thin flex-1 overflow-y-auto px-3 py-2 font-mono text-[11px]"
      >
        {logs.length === 0 && (
          <div className="rounded-md border border-dashed p-3 text-center text-muted-foreground">
            {t("runLog.empty")}
          </div>
        )}
        {logs.map((ev, i) => (
          <div
            key={i}
            className={cn("mb-1.5", isNestedEvent(ev) && "ml-3 border-l-2 border-amber-500/40 pl-2")}
          >
            <div
              className={cn(
                "whitespace-pre-wrap break-all",
                eventClasses[ev.event] ?? "text-foreground",
              )}
            >
              {formatLine(ev, t)}
            </div>
            {ev.event === "node_completed" &&
              (ev.output !== undefined || itemsCountFromEvent(ev) !== undefined) && (
              <OutputBlock
                output={previewFromEvent(ev)}
                itemsCount={itemsCountFromEvent(ev)}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
