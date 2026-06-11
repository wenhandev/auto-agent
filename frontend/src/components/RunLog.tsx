import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "@/store";
import type { RunEvent } from "@/types";
import { cn } from "@/lib/utils";
import { ResultPanel } from "./ResultPanel";

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

function formatLine(ev: RunEvent): string {
  const parts: string[] = [`[${formatTs(ev.ts)}]`, ev.event];
  if (ev.node_id) parts.push(ev.node_id);
  const tail = ev.message ?? ev.error;
  if (tail) parts.push(tail);
  return parts.join(" ");
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

interface OutputBlockProps {
  output: unknown;
}

function OutputBlock({ output }: OutputBlockProps) {
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
  run_completed: "text-emerald-400",
  run_failed: "text-destructive",
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
          <div key={i} className="mb-1.5">
            <div
              className={cn(
                "whitespace-pre-wrap break-all",
                eventClasses[ev.event] ?? "text-foreground",
              )}
            >
              {formatLine(ev)}
            </div>
            {ev.event === "node_completed" && ev.output !== undefined && (
              <OutputBlock output={ev.output} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
