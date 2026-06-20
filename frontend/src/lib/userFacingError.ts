import type { RunEventOut } from "@/types-platform";

const TECHNICAL_MARKERS = [
  "traceback",
  "playwright",
  "locator.",
  "call log:",
  "timeout 30000ms",
  "subtree intercepts",
  "get_by_role",
  "exception:",
  "httpx.",
];

export const REASON_CODES = new Set([
  "no_progress",
  "time_budget_exhausted",
  "step_budget_exhausted",
  "error",
  "guardrail",
  "schema_validation_failed",
  "aborted",
]);

export function isTechnicalError(text: string | null | undefined): boolean {
  if (!text?.trim()) return false;
  const lowered = text.toLowerCase();
  return TECHNICAL_MARKERS.some((marker) => lowered.includes(marker));
}

export function isReasonCode(reason: string | null | undefined): boolean {
  return Boolean(reason && REASON_CODES.has(reason));
}

function eventName(ev: RunEventOut): string {
  return ev.event_type || String(ev.payload?.event ?? "");
}

function objectiveLanguage(objective?: string | null): "zh" | "en" {
  return objective && /[\u4e00-\u9fff]/.test(objective) ? "zh" : "en";
}

function reasonCodeMessage(reason: string, lang: "zh" | "en"): string {
  const zh: Record<string, string> = {
    no_progress: "智能体在页面上停滞不前，无法继续完成任务。",
    time_budget_exhausted: "任务超时，未能完成目标。",
    step_budget_exhausted: "任务步数用尽，未能完成目标。",
    error: "浏览器操作出错，任务未能完成。",
    guardrail: "任务因安全或导航限制被阻止。",
    schema_validation_failed: "收集到的数据不符合要求的格式。",
    aborted: "任务已取消。",
  };
  const en: Record<string, string> = {
    no_progress: "The agent stopped making progress and could not continue.",
    time_budget_exhausted: "The task ran out of time before completing.",
    step_budget_exhausted: "The task used all allowed steps before completing.",
    error: "The task could not be completed due to a browser error.",
    guardrail: "The task was blocked by a safety or navigation rule.",
    schema_validation_failed: "Collected data did not match the required format.",
    aborted: "The task was cancelled.",
  };
  return (lang === "zh" ? zh : en)[reason] ?? (lang === "zh" ? "任务未能完成。" : "The task could not be completed.");
}

export function extractFailureFromEvents(
  events: RunEventOut[],
  _objective?: string | null,
  options?: { terminalOnly?: boolean },
): string | null {
  const terminalOnly = options?.terminalOnly ?? true;

  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    const name = eventName(ev);
    if (name === "task_finished") {
      const result = ev.payload?.result;
      if (result && typeof result === "object") {
        const r = result as Record<string, unknown>;
        if (terminalOnly && r.success !== false) continue;
        const userMessage = String(r.user_message ?? "").trim();
        if (userMessage) return userMessage;
        const summary = String(r.summary ?? "").trim();
        if (summary && !isTechnicalError(summary)) return summary;
        const reason = String(r.reason ?? "").trim();
        if (reason && !isReasonCode(reason) && !isTechnicalError(reason)) return reason;
      }
    }
    if (name === "run_failed") {
      const err = String(ev.payload?.error ?? "").trim();
      if (err && !isTechnicalError(err)) return err;
    }
  }

  if (terminalOnly) return null;

  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    if (eventName(ev) !== "vision_step") continue;
    const result = ev.payload?.result;
    if (!result || typeof result !== "object") continue;
    const err = String((result as Record<string, unknown>).error ?? "").trim();
    if (err && !isTechnicalError(err)) return err;
  }

  return null;
}

export function userFacingFailureMessage(input: {
  userMessage?: string | null;
  summary?: string | null;
  reason?: string | null;
  error?: string | null;
  objective?: string | null;
  events?: RunEventOut[];
  fallbackGeneric?: boolean;
}): string | null {
  const {
    userMessage,
    summary,
    reason,
    error,
    objective,
    events,
    fallbackGeneric = false,
  } = input;
  const lang = objectiveLanguage(objective);

  if (userMessage?.trim()) return userMessage.trim();
  if (summary?.trim() && !isTechnicalError(summary)) return summary.trim();
  if (reason?.trim() && !isReasonCode(reason) && !isTechnicalError(reason)) {
    return reason.trim();
  }
  if (error?.trim() && !isTechnicalError(error)) return error.trim();

  if (events?.length) {
    const fromEvents = extractFailureFromEvents(events, objective, {
      terminalOnly: true,
    });
    if (fromEvents) return fromEvents;
  }

  if (reason && isReasonCode(reason)) {
    return reasonCodeMessage(reason, lang);
  }

  if (fallbackGeneric) {
    return lang === "zh" ? "任务未能完成。" : "The task could not be completed.";
  }

  return null;
}
