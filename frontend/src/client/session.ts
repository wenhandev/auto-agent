import type { DesktopSession, WorkerApprovalStatus } from "./types";

const SESSION_KEY = "auto-agent.desktop.session";
const MACHINE_ID_KEY = "auto-agent.desktop.machine_id";

export function getOrCreateMachineId(): string {
  try {
    const existing = localStorage.getItem(MACHINE_ID_KEY);
    if (existing && existing.length >= 8) return existing;
  } catch {
    // ignore
  }
  const id = crypto.randomUUID();
  try {
    localStorage.setItem(MACHINE_ID_KEY, id);
  } catch {
    // ignore
  }
  return id;
}

export function loadSession(): DesktopSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as DesktopSession;
    if (!data.cloudUrl || !data.workerSessionToken) return null;
    if (!data.webSessionToken) {
      return { ...data, webSessionToken: "" };
    }
    return data;
  } catch {
    return null;
  }
}

export function saveSession(session: DesktopSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

export function updateApprovalStatus(status: WorkerApprovalStatus): void {
  const session = loadSession();
  if (!session) return;
  saveSession({ ...session, approvalStatus: status });
}
