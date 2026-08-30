import { http } from "@/api-platform";

export type UserSaidEvent = {
  kind: "user_said";
  seq: number;
  at: string;
  text: string;
  client_id: string;
};

export type ConversationEvent =
  | UserSaidEvent
  | { kind: "turn_started"; seq: number; at: string }
  | { kind: "turn_ended"; seq: number; at: string }
  | { kind: "stage_bound"; seq: number; at: string }
  | { kind: "control_changed"; seq: number; at: string };

export type DispatchNext = {
  kind: "dispatch";
  message_seq: number;
  objective: string;
  continues_turn_id: string | null;
  stage: { value: string; kind: string } | null;
};

export type HoldNext = {
  kind: "hold";
  why: "turn_running" | "human_driving" | "nothing_pending" | "closed";
};

export type NextStep = DispatchNext | HoldNext;

export type ConversationView = {
  id: string;
  title: string;
  closed: boolean;
  pending_count: number;
  awaiting_answer: boolean;
  events: ConversationEvent[];
  control_hint: "agent" | "human";
  next: NextStep;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseUserSaid(value: Record<string, unknown>): UserSaidEvent {
  if (
    typeof value.seq !== "number" ||
    typeof value.at !== "string" ||
    typeof value.text !== "string" ||
    typeof value.client_id !== "string"
  ) {
    throw new Error("invalid user_said event");
  }
  return {
    kind: "user_said",
    seq: value.seq,
    at: value.at,
    text: value.text,
    client_id: value.client_id,
  };
}

function parseEvent(value: unknown): ConversationEvent {
  if (!isRecord(value) || typeof value.kind !== "string") {
    throw new Error("invalid conversation event");
  }
  if (typeof value.seq !== "number" || typeof value.at !== "string") {
    throw new Error("invalid conversation event");
  }
  switch (value.kind) {
    case "user_said":
      return parseUserSaid(value);
    case "turn_started":
    case "turn_ended":
    case "stage_bound":
    case "control_changed":
      return { kind: value.kind, seq: value.seq, at: value.at };
    default:
      throw new Error(`unknown event kind: ${value.kind}`);
  }
}

function parseNext(value: unknown): NextStep {
  if (!isRecord(value) || typeof value.kind !== "string") {
    throw new Error("invalid conversation next");
  }
  if (value.kind === "dispatch") {
    if (
      typeof value.message_seq !== "number" ||
      typeof value.objective !== "string"
    ) {
      throw new Error("invalid dispatch next");
    }
    return {
      kind: "dispatch",
      message_seq: value.message_seq,
      objective: value.objective,
      continues_turn_id:
        typeof value.continues_turn_id === "string"
          ? value.continues_turn_id
          : null,
      stage: isRecord(value.stage) ? { value: String(value.stage.value), kind: String(value.stage.kind) } : null,
    };
  }
  if (value.kind === "hold") {
    if (
      value.why !== "turn_running" &&
      value.why !== "human_driving" &&
      value.why !== "nothing_pending" &&
      value.why !== "closed"
    ) {
      throw new Error("invalid hold next");
    }
    return { kind: "hold", why: value.why };
  }
  throw new Error("invalid conversation next");
}

function parseView(value: unknown): ConversationView {
  if (!isRecord(value)) {
    throw new Error("invalid conversation view");
  }
  if (
    typeof value.id !== "string" ||
    typeof value.title !== "string" ||
    typeof value.closed !== "boolean" ||
    typeof value.pending_count !== "number" ||
    typeof value.awaiting_answer !== "boolean" ||
    !Array.isArray(value.events) ||
    (value.control_hint !== "agent" && value.control_hint !== "human")
  ) {
    throw new Error("invalid conversation view");
  }
  return {
    id: value.id,
    title: value.title,
    closed: value.closed,
    pending_count: value.pending_count,
    awaiting_answer: value.awaiting_answer,
    events: value.events.map(parseEvent),
    control_hint: value.control_hint,
    next: parseNext(value.next),
  };
}

export function start(): Promise<ConversationView> {
  return http("POST", "/api/conversations").then(parseView);
}

export function get(id: string): Promise<ConversationView> {
  return http(
    "GET",
    `/api/conversations/${encodeURIComponent(id)}`,
  ).then(parseView);
}

export function send(
  id: string,
  text: string,
  clientId: string,
): Promise<ConversationView> {
  return http("POST", `/api/conversations/${encodeURIComponent(id)}/messages`, {
    text,
    client_id: clientId,
  }).then(parseView);
}

export function isUserSaid(event: ConversationEvent): event is UserSaidEvent {
  return event.kind === "user_said";
}
