/** Product policy for the cloud-hosted web admin UI (not the Tauri desktop shell). */
export const webPlatformPolicy = {
  /** New workflows are authored in the desktop client; web is view, run, and admin. */
  canCreateWorkflows: false,
  showRecordings: false,
  showBrowserSessions: false,
  showBrowserProfiles: false,
  /** Credential vault lives on the worker/desktop machine, not in cloud storage. */
  showCloudCredentials: false,
} as const;

export type WebPlatformPolicy = typeof webPlatformPolicy;

export type DesktopOnlyFeatureKey =
  | "recordings"
  | "browserSessions"
  | "browserProfiles"
  | "credentials";
