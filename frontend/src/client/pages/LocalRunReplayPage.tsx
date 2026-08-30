import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";
import { LiveStreamPanel } from "@/components/LiveStreamPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { RunEvent } from "@/types";
import { DesktopApiError, fetchLocalRun } from "../api";
import { subscribeRunEvents } from "../runtimeBridge";
import type { LocalRunMeta } from "../types";

function eventLabel(ev: RunEvent): string {
  if (!ev.event) return "";
  const node = ev.node_id ? ` [${ev.node_id}]` : "";
  return `${ev.event}${node}`;
}

export function LocalRunReplayPage() {
  const { t } = useTranslation();
  const { runId } = useParams<{ runId: string }>();
  const [meta, setMeta] = useState<LocalRunMeta | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);

  const refreshMeta = useCallback(async () => {
    if (!runId) return;
    try {
      const row = await fetchLocalRun(runId);
      setMeta(row);
      setError(null);
    } catch (err) {
      setError(
        err instanceof DesktopApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
    }
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    void refreshMeta().finally(() => setLoading(false));
  }, [runId, refreshMeta]);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setEvents([]);

    void subscribeRunEvents(runId, (data) => {
      if (cancelled) return;
      try {
        const raw = JSON.parse(data) as RunEvent;
        setEvents((prev) => [...prev, raw]);
        const terminal = raw.event;
        if (
          terminal === "run_completed" ||
          terminal === "run_completed_with_errors" ||
          terminal === "run_failed" ||
          terminal === "run_aborted" ||
          terminal === "run_rejected"
        ) {
          void refreshMeta();
        }
      } catch {
        // ignore malformed events
      }
    });

    return () => {
      cancelled = true;
    };
  }, [runId, refreshMeta]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events]);

  const running = meta?.status === "running";

  if (!runId) {
    return null;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-6">
      <div className="flex shrink-0 items-start gap-3">
        <Button asChild variant="ghost" size="icon" className="mt-0.5 shrink-0">
          <Link to="/runs/console" aria-label={t("desktop.runs.backToConsole")}>
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-semibold tracking-tight">
            {t("desktop.runs.localReplayTitle", { id: runId })}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("desktop.runs.localReplaySubtitle")}
          </p>
        </div>
        {meta && (
          <Badge variant={running ? "default" : "secondary"}>
            {t(`status.${meta.status}`, meta.status)}
          </Badge>
        )}
      </div>

      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {loading && !meta && (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      )}

      {meta && (
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                {t("desktop.runs.eventLog")}
              </CardTitle>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
              <div
                ref={logRef}
                className="scrollbar-thin h-full max-h-[520px] overflow-y-auto px-3 py-2 font-mono text-[11px]"
              >
                {events.length === 0 ? (
                  <p className="text-muted-foreground">
                    {running
                      ? t("desktop.runs.waitingEvents")
                      : t("desktop.runs.noEvents")}
                  </p>
                ) : (
                  events.map((ev, i) => {
                    const label = eventLabel(ev);
                    if (!label) return null;
                    return (
                      <div key={i} className="mb-1 whitespace-pre-wrap break-all">
                        <span className="text-muted-foreground">{ev.ts} </span>
                        {label}
                        {ev.error ? (
                          <span className="text-destructive"> — {ev.error}</span>
                        ) : null}
                      </div>
                    );
                  })
                )}
              </div>
            </CardContent>
          </Card>
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
              <LiveStreamPanel runId={runId} active={running} runtimeRelay />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
