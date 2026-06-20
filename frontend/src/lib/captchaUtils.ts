import type { RunEventOut, PendingApproval } from "@/types-platform";

export type CaptchaKind =
  | "recaptcha"
  | "hcaptcha"
  | "turnstile"
  | "slider"
  | "unknown"
  | string;

export interface CaptchaRunState {
  detected: boolean;
  kind: CaptchaKind | null;
  awaitingApproval: boolean;
  solved: boolean;
  showBanner: boolean;
}

function payloadKind(payload: Record<string, unknown>): CaptchaKind | null {
  const kind = payload.kind ?? payload.captcha_kind;
  return typeof kind === "string" ? kind : null;
}

function isCaptchaApprovalEvent(payload: Record<string, unknown>): boolean {
  if (payload.captcha_kind != null) return true;
  const prompt = payload.prompt;
  if (typeof prompt === "string" && /captcha/i.test(prompt)) return true;
  const schema = payload.inputs_schema;
  if (Array.isArray(schema)) {
    return schema.some(
      (item) =>
        item &&
        typeof item === "object" &&
        (item as { name?: string }).name === "captcha_solved",
    );
  }
  return false;
}

export function deriveCaptchaRunState(events: RunEventOut[]): CaptchaRunState {
  let kind: CaptchaKind | null = null;
  let detected = false;
  let awaitingApproval = false;
  let solved = false;

  for (const ev of events) {
    switch (ev.event_type) {
      case "captcha_detected":
        detected = true;
        kind = payloadKind(ev.payload) ?? kind;
        solved = false;
        break;
      case "captcha_solved":
        solved = true;
        awaitingApproval = false;
        break;
      case "captcha_unsolved":
        solved = false;
        break;
      case "node_awaiting_approval":
        if (isCaptchaApprovalEvent(ev.payload)) {
          awaitingApproval = true;
          kind = payloadKind(ev.payload) ?? kind;
        }
        break;
      case "node_approved":
      case "node_rejected":
        awaitingApproval = false;
        break;
      default:
        break;
    }
  }

  return {
    detected,
    kind,
    awaitingApproval,
    solved,
    showBanner: detected && !solved,
  };
}

export function isCaptchaApproval(pending: PendingApproval | null | undefined): boolean {
  if (!pending) return false;
  if (pending.captcha_kind) return true;
  if (/captcha/i.test(pending.prompt)) return true;
  return pending.inputs_schema.some((spec) => spec.name === "captcha_solved");
}

export function captchaKindLabel(
  kind: CaptchaKind | null | undefined,
  t: (key: string, fallback?: string) => string,
): string {
  if (!kind) {
    return t("captcha.kind.unknown", "Unknown");
  }
  return t(`captcha.kind.${kind}`, kind);
}
