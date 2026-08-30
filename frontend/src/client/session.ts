import type { DesktopSession, WorkerApprovalStatus } from "./types";
import {
  desktopDefaultCloudUrl,
  isLocalDevCloudUrl,
} from "./cloudUrl";

const SESSION_KEY = "auto-agent.desktop.session";
const MACHINE_ID_KEY = "auto-agent.desktop.machine_id";

const GENERIC_DISPLAY_NAMES = new Set(
  ["localhost", "127.0.0.1", "my device", "desktop", "unknown"].map((s) =>
    s.toLowerCase(),
  ),
);

export function isGenericDisplayName(name: string | undefined | null): boolean {
  const trimmed = name?.trim();
  if (!trimmed) return true;
  return GENERIC_DISPLAY_NAMES.has(trimmed.toLowerCase());
}

/** Normalize persisted session after upgrades (cloud URL, display name). */
export function migrateSession(session: DesktopSession): DesktopSession {
  const bakedCloud = desktopDefaultCloudUrl().replace(/\/$/, "");
  let cloudUrl = session.cloudUrl.trim().replace(/\/$/, "");
  if (
    bakedCloud &&
    isLocalDevCloudUrl(cloudUrl) &&
    !isLocalDevCloudUrl(bakedCloud)
  ) {
    cloudUrl = bakedCloud;
  }
  const displayName = isGenericDisplayName(session.displayName)
    ? session.displayName
    : session.displayName.trim();
  return { ...session, cloudUrl, displayName };
}

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
    const session = migrateSession({
      ...data,
      webSessionToken: data.webSessionToken || "",
    });
    return session;
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
