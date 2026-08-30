import i18n from "@/i18n";
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

function reasonCodeMessage(reason: string): string {
  const key = `taskFailure.reasons.${reason}`;
  const translated = i18n.t(key);
  return translated !== key ? translated : i18n.t("taskFailure.generic");
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
    const name = eventName(ev);
    if (name !== "vision_step" && name !== "desktop_step") continue;
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
    objective: _objective,
    events,
    fallbackGeneric = false,
  } = input;

  if (userMessage?.trim()) return userMessage.trim();
  if (summary?.trim() && !isTechnicalError(summary)) return summary.trim();
  if (reason?.trim() && !isReasonCode(reason) && !isTechnicalError(reason)) {
    return reason.trim();
  }
  if (error?.trim() && !isTechnicalError(error)) return error.trim();

  if (events?.length) {
    const fromEvents = extractFailureFromEvents(events, _objective, {
      terminalOnly: true,
    });
    if (fromEvents) return fromEvents;
  }

  if (reason && isReasonCode(reason)) {
    return reasonCodeMessage(reason);
  }

  if (fallbackGeneric) {
    return i18n.t("taskFailure.generic");
  }

  return null;
}
