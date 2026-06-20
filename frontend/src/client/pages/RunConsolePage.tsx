import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Square } from "lucide-react";
import { LiveStreamPanel } from "@/components/LiveStreamPanel";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import type { RunEvent } from "@/types";
import {
  abortLocalRun,
  DesktopApiError,
  fetchCloudWorkflows,
  listLocalRuns,
  localRunEventsUrl,
  localStreamWsUrl,
  startLocalRun,
} from "../api";
import type { CloudWorkflowListItem, LocalRunMeta } from "../types";

function eventLabel(ev: RunEvent): string {
  const node = ev.node_id ? ` [${ev.node_id}]` : "";
  return `${ev.event}${node}`;
}

export function RunConsolePage() {
  const [workflows, setWorkflows] = useState<CloudWorkflowListItem[]>([]);
  const [history, setHistory] = useState<LocalRunMeta[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>("");
  const [activeRun, setActiveRun] = useState<LocalRunMeta | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const refreshMeta = useCallback(async () => {
    try {
      const [wf, runs] = await Promise.all([
        fetchCloudWorkflows(),
        listLocalRuns(),
      ]);
      setWorkflows(wf);
      setHistory(runs);
      if (!selectedWorkflowId && wf.length > 0) {
        setSelectedWorkflowId(wf[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [selectedWorkflowId]);

  useEffect(() => {
    void refreshMeta();
  }, [refreshMeta]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events]);

  useEffect(() => {
    if (!activeRun || activeRun.status !== "running") {
      sourceRef.current?.close();
      sourceRef.current = null;
      return;
    }
    const source = new EventSource(localRunEventsUrl(activeRun.id));
    sourceRef.current = source;
    source.onmessage = (msg) => {
      try {
        const raw = JSON.parse(msg.data) as RunEvent;
        setEvents((prev) => [...prev, raw]);
        const terminal = raw.event;
        if (
          terminal === "run_completed" ||
          terminal === "run_completed_with_errors" ||
          terminal === "run_failed" ||
          terminal === "run_aborted" ||
          terminal === "run_rejected"
        ) {
          setActiveRun((prev) =>
            prev ? { ...prev, status: String(terminal).replace("run_", "") } : prev,
          );
          void refreshMeta();
        }
      } catch {
        // ignore malformed events
      }
    };
    source.onerror = () => {
      source.close();
    };
    return () => {
      source.close();
    };
  }, [activeRun?.id, activeRun?.status, refreshMeta]);

  async function onRun() {
    if (!selectedWorkflowId) return;
    setError(null);
    setLoading(true);
    setEvents([]);
    try {
      const meta = await startLocalRun({ workflow_id: selectedWorkflowId });
      setActiveRun(meta);
      void refreshMeta();
    } catch (err) {
      setError(
        err instanceof DesktopApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setLoading(false);
    }
  }

  async function onAbort() {
    if (!activeRun) return;
    try {
      await abortLocalRun(activeRun.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const running = activeRun?.status === "running";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Run console</h1>
        <p className="text-sm text-muted-foreground">
          Execute workflows locally via the runtime sidecar.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Start run</CardTitle>
          <CardDescription>Workflows from your cloud organisation</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <Select value={selectedWorkflowId} onValueChange={setSelectedWorkflowId}>
              <SelectTrigger>
                <SelectValue placeholder="Select workflow" />
              </SelectTrigger>
              <SelectContent>
                {workflows.map((wf) => (
                  <SelectItem key={wf.id} value={wf.id}>
                    {wf.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={() => void onRun()} disabled={loading || running || !selectedWorkflowId}>
            <Play className="mr-2 h-4 w-4" />
            Run locally
          </Button>
          {running && activeRun && (
            <Button variant="destructive" onClick={() => void onAbort()}>
              <Square className="mr-2 h-4 w-4" />
              Abort
            </Button>
          )}
        </CardContent>
      </Card>

      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {activeRun && (
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">Run {activeRun.id}</CardTitle>
                <Badge variant={running ? "default" : "secondary"}>
                  {activeRun.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
              <div
                ref={logRef}
                className="scrollbar-thin h-full max-h-[420px] overflow-y-auto px-3 py-2 font-mono text-[11px]"
              >
                {events.length === 0 ? (
                  <p className="text-muted-foreground">Waiting for events…</p>
                ) : (
                  events.map((ev, i) => (
                    <div key={i} className="mb-1 whitespace-pre-wrap break-all">
                      <span className="text-muted-foreground">{ev.ts} </span>
                      {eventLabel(ev)}
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
              <LiveStreamPanel
                runId={activeRun.id}
                active={running}
                streamWsUrl={localStreamWsUrl(activeRun.id)}
              />
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent local runs</CardTitle>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No local runs yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {history.slice(0, 10).map((run) => (
                <li key={run.id} className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-xs">{run.id}</span>
                  <Badge variant="outline">{run.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
