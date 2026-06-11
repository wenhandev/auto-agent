import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ReactFlowProvider } from "@xyflow/react";
import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import { apiClient } from "@/api-platform";
import { RunLog } from "@/components/RunLog";
import { WorkflowCanvas } from "@/components/WorkflowCanvas";
import { useStore } from "@/store";
import { usePlatformStore } from "@/platformStore";
import type { RunEventOut, RunReplayResponse } from "@/types-platform";
import type { RunEvent, RunEventType } from "@/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { statusBadgeVariant } from "@/lib/status";

const SPEEDS = [0.5, 1, 2, 5] as const;
type ReplaySpeed = (typeof SPEEDS)[number];

function eventOutToRunEvent(ev: RunEventOut): RunEvent {
  const payload = ev.payload ?? {};
  return {
    event: ev.event_type as RunEventType,
    node_id: ev.node_id ?? undefined,
    ts: ev.ts,
    message: typeof payload.message === "string" ? payload.message : undefined,
    output: payload.output,
    error: typeof payload.error === "string" ? payload.error : undefined,
  };
}

function resetToInitial(data: RunReplayResponse) {
  useStore.getState().setWorkflow(data.workflow_version.workflow);
  usePlatformStore.getState().setCurrentWorkflow(
    data.run.workflow_id,
    data.workflow_version.workflow,
    data.workflow_version,
  );
}

function applyEventToStore(ev: RunEventOut) {
  const runEvent = eventOutToRunEvent(ev);
  useStore.getState().applyEvent(runEvent);
}

export function RunReplayPage() {
  const { t } = useTranslation();
  const { runId } = useParams<{ runId: string }>();
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(1);
  const timerRef = useRef<number | null>(null);

  const replayQuery = useQuery({
    queryKey: ["runs", "replay", runId ?? ""],
    queryFn: () => apiClient.runs.replay(runId!),
    enabled: !!runId,
  });

  const events = useMemo(
    () => replayQuery.data?.events ?? [],
    [replayQuery.data],
  );

  useEffect(() => {
    if (replayQuery.data) {
      resetToInitial(replayQuery.data);
      setCursor(0);
      setPlaying(false);
    }
  }, [replayQuery.data]);

  useEffect(() => {
    if (!playing) {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    if (cursor >= events.length) {
      setPlaying(false);
      return;
    }
    const current = events[cursor];
    const next = events[cursor + 1];
    let delay = 250;
    if (next) {
      const cur = new Date(current.ts).getTime();
      const nxt = new Date(next.ts).getTime();
      if (!Number.isNaN(cur) && !Number.isNaN(nxt) && nxt > cur) {
        delay = Math.min(Math.max((nxt - cur) / speed, 30), 2000);
      }
    }
    applyEventToStore(current);
    timerRef.current = window.setTimeout(() => {
      setCursor((c) => c + 1);
    }, delay);
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [playing, cursor, events, speed]);

  function onPlayPause() {
    if (!events.length) return;
    if (cursor >= events.length) {
      restart();
      return;
    }
    setPlaying((p) => !p);
  }

  function onStep() {
    if (cursor >= events.length) return;
    applyEventToStore(events[cursor]);
    setCursor((c) => c + 1);
  }

  function restart() {
    setPlaying(false);
    if (replayQuery.data) {
      resetToInitial(replayQuery.data);
    }
    setCursor(0);
  }

  if (!runId) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("pages.runReplay.noRunId")}
      </div>
    );
  }

  if (replayQuery.isLoading) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("pages.runReplay.loading")}
      </div>
    );
  }

  if (replayQuery.error) {
    return (
      <div className="p-6 text-sm text-destructive">
        {(replayQuery.error as Error).message}
      </div>
    );
  }

  if (!replayQuery.data) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("pages.runReplay.notFound")}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b bg-card/40 px-4 py-2">
        <Button
          size="sm"
          variant="outline"
          onClick={onPlayPause}
          disabled={!events.length}
        >
          {playing ? (
            <Pause className="mr-1.5 h-3.5 w-3.5" />
          ) : (
            <Play className="mr-1.5 h-3.5 w-3.5" />
          )}
          {playing ? t("pages.runReplay.pause") : t("pages.runReplay.play")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onStep}
          disabled={playing || cursor >= events.length}
        >
          <StepForward className="mr-1.5 h-3.5 w-3.5" />
          {t("pages.runReplay.step")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={restart}
          disabled={!events.length}
        >
          <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
          {t("pages.runReplay.restart")}
        </Button>
        <Select
          value={String(speed)}
          onValueChange={(v) => setSpeed(Number(v) as ReplaySpeed)}
        >
          <SelectTrigger className="h-8 w-[88px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SPEEDS.map((s) => (
              <SelectItem key={s} value={String(s)}>
                {t("pages.runReplay.speedLabel", { n: s })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-xs text-muted-foreground">
          {t("pages.runReplay.progress", {
            cursor,
            total: events.length,
          })}
        </span>
        <Badge variant={statusBadgeVariant(replayQuery.data.run.status)}>
          {t(
            `status.${replayQuery.data.run.status}`,
            replayQuery.data.run.status,
          )}
        </Badge>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 border-r">
          <ReactFlowProvider>
            <WorkflowCanvas />
          </ReactFlowProvider>
        </div>
        <div className="flex w-[380px] shrink-0 min-h-0 flex-col">
          <RunLog />
        </div>
      </div>
    </div>
  );
}
