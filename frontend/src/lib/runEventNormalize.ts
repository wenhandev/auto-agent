import type { RunEvent, RunEventType } from "@/types";
import type { RunEventOut, WSEvent } from "@/types-platform";

function applyPayloadFields(event: RunEvent, payload: Record<string, unknown>): void {
  if (typeof payload.message === "string") event.message = payload.message;
  if (payload.output !== undefined) event.output = payload.output;
  if (typeof payload.error === "string") event.error = payload.error;
  if (typeof payload.attempt === "number") event.attempt = payload.attempt;
  if (typeof payload.error_kind === "string") event.error_kind = payload.error_kind;
  if (typeof payload.next_attempt_at === "string") {
    event.next_attempt_at = payload.next_attempt_at;
  }
  if (typeof payload.failed_node_count === "number") {
    event.failed_node_count = payload.failed_node_count;
  }
  if (Array.isArray(payload.failed_node_ids)) {
    event.failed_node_ids = payload.failed_node_ids as string[];
  }
  if (typeof payload.prompt === "string") event.prompt = payload.prompt;
  if (typeof payload.decision === "string") event.decision = payload.decision;
  if (typeof payload.original_selector === "string") {
    event.original_selector = payload.original_selector;
  }
  if ("new_selector" in payload) {
    event.new_selector =
      typeof payload.new_selector === "string" ? payload.new_selector : null;
  }
  if (typeof payload.confidence === "number") event.confidence = payload.confidence;
  if (typeof payload.mode === "string") event.mode = payload.mode;
  if (typeof payload.reason === "string") event.reason = payload.reason;
  if (typeof payload.selector === "string") event.selector = payload.selector;
  if (typeof payload.url_pattern === "string") event.url_pattern = payload.url_pattern;
  if (typeof payload.cache_entry_id === "string") {
    event.cache_entry_id = payload.cache_entry_id;
  }
  if ("post_heal_error" in payload) {
    event.post_heal_error =
      typeof payload.post_heal_error === "string"
        ? payload.post_heal_error
        : null;
  }
  if (typeof payload.items_count === "number") {
    event.items_count = payload.items_count;
  }
  if (payload.items_preview && typeof payload.items_preview === "object") {
    event.items_preview = payload.items_preview as RunEvent["items_preview"];
  }
  if (typeof payload.edge_id === "string") event.edge_id = payload.edge_id;
  if (typeof payload.arrived === "number") event.arrived = payload.arrived;
  if (typeof payload.expected === "number") event.expected = payload.expected;
}

export function runEventOutToRunEvent(ev: RunEventOut): RunEvent {
  const payload = ev.payload ?? {};
  const event: RunEvent = {
    event: ev.event_type as RunEventType,
    node_id: ev.node_id ?? undefined,
    ts: ev.ts,
    payload,
  };
  applyPayloadFields(event, payload);
  return event;
}

export function wsEventToRunEvent(frame: WSEvent): RunEvent {
  const raw = frame as WSEvent & Record<string, unknown>;
  const payload = (raw.payload as Record<string, unknown> | undefined) ?? {};
  const event: RunEvent = {
    event: frame.event as RunEventType,
    node_id: frame.node_id ?? undefined,
    ts: frame.ts,
    message: frame.message ?? undefined,
    output: frame.output,
    error: frame.error ?? undefined,
    payload,
  };
  applyPayloadFields(event, { ...payload, ...raw });
  return event;
}

export function pickRunEventField(ev: RunEvent, key: string): unknown {
  if (ev.payload && key in ev.payload) {
    return ev.payload[key];
  }
  return (ev as unknown as Record<string, unknown>)[key];
}
