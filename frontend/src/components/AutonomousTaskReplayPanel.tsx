import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Bot, ListChecks, Loader2, Target } from "lucide-react";
import type { RunEventOut, RunOut, TaskResultOut } from "@/types-platform";
import { Badge } from "@/components/ui/badge";
import { statusBadgeVariant } from "@/lib/status";
import { userFacingFailureMessage } from "@/lib/userFacingError";

interface PlanItem {
  id?: string;
  text?: string;
  status?: string;
}

interface VisionStep {
  stepIndex: number;
  thought: string;
  action: string;
  ts: string;
}

function eventName(ev: RunEventOut): string {
  return ev.event_type || String(ev.payload?.event ?? "");
}

function extractPlan(events: RunEventOut[]): PlanItem[] {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    if (eventName(ev) !== "task_plan_updated") continue;
    const plan = ev.payload?.plan;
    if (Array.isArray(plan)) return plan as PlanItem[];
  }
  return [];
}

function extractVisionSteps(events: RunEventOut[]): VisionStep[] {
  return events
    .filter((ev) => eventName(ev) === "vision_step")
    .map((ev) => ({
      stepIndex: Number(ev.payload?.step_index ?? 0),
      thought: String(ev.payload?.thought ?? ""),
      action: String(ev.payload?.action ?? ""),
      ts: ev.ts,
    }));
}

function extractTaskResult(
  run: RunOut,
  events: RunEventOut[],
): TaskResultOut | null {
  if (run.task_result) return run.task_result;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    if (eventName(ev) !== "task_finished") continue;
    const result = ev.payload?.result;
    if (result && typeof result === "object") {
      return result as TaskResultOut;
    }
  }
  return null;
}

interface Props {
  run: RunOut;
  events: RunEventOut[];
}

export function AutonomousTaskReplayPanel({ run, events }: Props) {
  const { t } = useTranslation();
  const plan = useMemo(() => extractPlan(events), [events]);
  const steps = useMemo(() => extractVisionSteps(events), [events]);
  const result = useMemo(
    () => extractTaskResult(run, events),
    [run, events],
  );

  const isRunning = run.status === "running" || run.status === "queued";
  const isFailed = run.status === "failed" || run.status === "aborted";
  const failureMessage = isFailed
    ? userFacingFailureMessage({
        userMessage: result?.user_message,
        summary: result?.summary,
        reason: result?.reason,
        error: run.error,
        objective: run.objective,
        events,
        fallbackGeneric: true,
      })
    : null;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto bg-muted/10 p-6">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Bot className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("pages.autonomousReplay.title")}
            </div>
            <h2 className="mt-1 text-lg font-semibold text-foreground">
              {run.objective || t("pages.autonomousReplay.noObjective")}
            </h2>
            {result && !isRunning && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge variant={statusBadgeVariant(result.success ? "completed" : "failed")}>
                  {result.success
                    ? t("pages.autonomousReplay.resultSuccess")
                    : t("pages.autonomousReplay.resultFailed")}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {t("pages.autonomousReplay.stepsTaken", {
                    count: result.steps_taken ?? 0,
                  })}
                </span>
              </div>
            )}
            {isRunning && (
              <div className="mt-2 flex items-center gap-2">
                <Badge variant={statusBadgeVariant("running")}>
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  {t("pages.autonomousReplay.running")}
                </Badge>
                {steps.length > 0 && (
                  <span className="text-sm text-muted-foreground">
                    {t("pages.autonomousReplay.stepsTaken", {
                      count: steps.length,
                    })}
                  </span>
                )}
              </div>
            )}
            {isFailed && !result && (
              <div className="mt-2">
                <Badge variant={statusBadgeVariant("failed")}>
                  {t("pages.autonomousReplay.resultFailed")}
                </Badge>
              </div>
            )}
          </div>
        </div>

        {isFailed && failureMessage && (
          <section className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-destructive">
              {t("pages.autonomousReplay.failureReason")}
            </div>
            <p className="whitespace-pre-wrap break-words text-sm text-foreground">
              {failureMessage}
            </p>
          </section>
        )}

        {result?.summary && result.success && (
          <section className="rounded-lg border bg-card p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t("pages.autonomousReplay.summary")}
            </div>
            <p className="text-sm text-foreground">{result.summary}</p>
            {result.reason && (
              <p className="mt-2 text-xs text-destructive">{result.reason}</p>
            )}
          </section>
        )}

        {plan.length > 0 && (
          <section className="rounded-lg border bg-card p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Target className="h-3.5 w-3.5" />
              {t("pages.autonomousReplay.plan")}
            </div>
            <ol className="space-y-2">
              {plan.map((item, idx) => (
                <li
                  key={item.id ?? idx}
                  className="flex items-start gap-2 text-sm"
                >
                  <Badge variant="outline" className="mt-0.5 shrink-0 text-[10px]">
                    {item.status ?? "pending"}
                  </Badge>
                  <span>{item.text}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section className="rounded-lg border bg-card p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <ListChecks className="h-3.5 w-3.5" />
            {t("pages.autonomousReplay.actions")}
          </div>
          {steps.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("pages.autonomousReplay.noActions")}
            </p>
          ) : (
            <ol className="space-y-3">
              {steps.map((step) => (
                <li
                  key={`${step.stepIndex}-${step.ts}`}
                  className="rounded-md border bg-muted/30 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="secondary" className="font-mono text-[10px]">
                      #{step.stepIndex + 1} {step.action}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground">
                      {new Date(step.ts).toLocaleTimeString()}
                    </span>
                  </div>
                  {step.thought && (
                    <p className="mt-1 text-sm text-foreground">{step.thought}</p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
