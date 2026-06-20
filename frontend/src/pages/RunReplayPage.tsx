import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ReactFlowProvider } from "@xyflow/react";
import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import { apiClient } from "@/api-platform";
import { ApprovalBanner } from "@/components/ApprovalBanner";
import { ArtifactsPanel } from "@/components/ArtifactsPanel";
import { CaptchaLiveBanner } from "@/components/CaptchaLiveBanner";
import { LiveStreamPanel } from "@/components/LiveStreamPanel";
import { AutonomousTaskReplayPanel } from "@/components/AutonomousTaskReplayPanel";
import { RunLog } from "@/components/RunLog";
import { WorkflowCanvas } from "@/components/WorkflowCanvas";
import { useStore } from "@/store";
import { usePlatformStore } from "@/platformStore";
import type { RunEventOut, RunReplayResponse } from "@/types-platform";
import { runEventOutToRunEvent } from "@/lib/runEventNormalize";
import { deriveCaptchaRunState } from "@/lib/captchaUtils";
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

function resetToInitial(data: RunReplayResponse) {
  useStore.getState().resetWorkflowForReplay(data.workflow_version.workflow);
  usePlatformStore.getState().syncWorkflowDefinition(
    data.run.workflow_id,
    data.workflow_version.workflow,
    data.workflow_version,
  );
}

function applyFullReplay(data: RunReplayResponse) {
  resetToInitial(data);
  for (const ev of data.events) {
    applyEventToStore(ev);
  }
}

function syncReplayFromQuery(data: RunReplayResponse, appliedEventCount: number) {
  useStore.getState().syncWorkflowGraph(data.workflow_version.workflow);
  usePlatformStore.getState().syncWorkflowDefinition(
    data.run.workflow_id,
    data.workflow_version.workflow,
    data.workflow_version,
  );

  const events = data.events;
  if (events.length <= appliedEventCount) {
    return appliedEventCount;
  }

  for (let i = appliedEventCount; i < events.length; i++) {
    applyEventToStore(events[i]);
  }
  return events.length;
}

function applyEventToStore(ev: RunEventOut) {
  const runEvent = runEventOutToRunEvent(ev);
  useStore.getState().applyEvent(runEvent);
}

export function RunReplayPage() {
  const { t } = useTranslation();
  const { runId } = useParams<{ runId: string }>();
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(1);
  const timerRef = useRef<number | null>(null);
  const appliedRunRef = useRef<string | null>(null);
  const appliedEventCountRef = useRef(0);

  const replayQuery = useQuery({
    queryKey: ["runs", "replay", runId ?? ""],
    queryFn: () => apiClient.runs.replay(runId!),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status === "running" || status === "queued" ? 3000 : false;
    },
  });

  const events = useMemo(
    () => replayQuery.data?.events ?? [],
    [replayQuery.data],
  );

  const captchaState = useMemo(
    () => deriveCaptchaRunState(events.slice(0, cursor)),
    [events, cursor],
  );

  const run = replayQuery.data?.run;
  const isAutonomousRun = run?.mode === "autonomous";
  const isActiveRun =
    run?.status === "running" || run?.status === "queued";
  const pendingApproval = run?.pending_approval ?? null;
  const pendingWithCaptcha = useMemo(() => {
    if (!pendingApproval) return null;
    if (pendingApproval.captcha_kind || !captchaState.kind) {
      return pendingApproval;
    }
    return { ...pendingApproval, captcha_kind: captchaState.kind };
  }, [pendingApproval, captchaState.kind]);
  const approvalRef = useRef<HTMLDivElement>(null);
  const hasCost =
    run &&
    ((run.total_input_tokens ?? 0) > 0 ||
      (run.total_output_tokens ?? 0) > 0 ||
      run.estimated_cost_usd != null);
  const loopMetrics = run?.agent_loop_metrics ?? null;
  const routeSkillCount = useMemo(
    () =>
      events.filter(
        (ev) =>
          ev.event_type === "route_skill_applied" ||
          ev.payload?.event === "route_skill_applied",
      ).length,
    [events],
  );

  useEffect(() => {
    const data = replayQuery.data;
    if (!data) return;

    const isNewRun = appliedRunRef.current !== data.run.id;
    if (isNewRun) {
      appliedRunRef.current = data.run.id;
      appliedEventCountRef.current = 0;
      applyFullReplay(data);
      appliedEventCountRef.current = data.events.length;
      setCursor(data.events.length);
      setPlaying(false);
      return;
    }

    appliedEventCountRef.current = syncReplayFromQuery(
      data,
      appliedEventCountRef.current,
    );
    setCursor((prev) => Math.max(prev, data.events.length));
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
    appliedEventCountRef.current = 0;
    if (replayQuery.data) {
      applyFullReplay(replayQuery.data);
      appliedEventCountRef.current = replayQuery.data.events.length;
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

  function scrollToApproval() {
    approvalRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {runId && isActiveRun && pendingWithCaptcha && (
        <div ref={approvalRef}>
          <ApprovalBanner
            runId={runId}
            pending={pendingWithCaptcha}
            onResolved={() => {
              void replayQuery.refetch();
            }}
          />
        </div>
      )}
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
        {isAutonomousRun && (
          <Badge variant="outline">{t("pages.runReplay.autonomousMode")}</Badge>
        )}
        {replayQuery.data.run.execution_mode === "worker" && (
          <Badge variant="outline">{t("pages.runReplay.workerMode")}</Badge>
        )}
        {replayQuery.data.run.queue_reason && (
          <Badge variant="secondary">
            {t(
              `pages.runHistory.queueReason.${replayQuery.data.run.queue_reason}`,
              replayQuery.data.run.queue_reason,
            )}
          </Badge>
        )}
        {replayQuery.data.run.worker_name && (
          <span className="text-xs text-muted-foreground">
            {replayQuery.data.run.worker_name}
          </span>
        )}
        {hasCost && run && (
          <span className="text-xs text-muted-foreground">
            {t("pages.runReplay.costSummary", {
              input: run.total_input_tokens ?? 0,
              output: run.total_output_tokens ?? 0,
              cost:
                run.estimated_cost_usd != null
                  ? `$${run.estimated_cost_usd.toFixed(4)}`
                  : t("pages.runReplay.costUnknown"),
            })}
          </span>
        )}
        {loopMetrics && (
          <div className="flex flex-wrap gap-1">
            <Badge variant="outline">
              {t("pages.runReplay.metricsRounds", {
                count: Number(loopMetrics.rounds ?? 0),
              })}
            </Badge>
            <Badge variant="outline">
              {t("pages.runReplay.metricsCache", {
                hits: Number(loopMetrics.cache_hits ?? 0),
                misses: Number(loopMetrics.cache_misses ?? 0),
              })}
            </Badge>
            {Number(loopMetrics.computer_use_fallbacks ?? 0) > 0 && (
              <Badge variant="secondary">
                {t("pages.runReplay.metricsFallback", {
                  count: Number(loopMetrics.computer_use_fallbacks ?? 0),
                })}
              </Badge>
            )}
            {routeSkillCount > 0 && (
              <Badge variant="secondary">
                {t("pages.runReplay.metricsRouteSkills", { count: routeSkillCount })}
              </Badge>
            )}
          </div>
        )}
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 border-r">
          {isAutonomousRun && run ? (
            <AutonomousTaskReplayPanel run={run} events={events} />
          ) : (
            <ReactFlowProvider key={runId}>
              <WorkflowCanvas />
            </ReactFlowProvider>
          )}
        </div>
        <div className="flex w-[380px] shrink-0 min-h-0 flex-col overflow-auto">
          <CaptchaLiveBanner
            state={captchaState}
            onOpenApproval={
              pendingWithCaptcha && isActiveRun ? scrollToApproval : undefined
            }
          />
          <LiveStreamPanel
            runId={runId}
            active={isActiveRun}
          />
          <ArtifactsPanel runId={runId} active={isActiveRun} />
          <RunLog />
        </div>
      </div>
    </div>
  );
}
