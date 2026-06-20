export const ROUTES = {
  root: "/",
  login: "/login",
  loginOAuthCallback: "/login/oauth/callback",
  clientDownload: "/client",
  workflows: "/workflows",
  workflowDetail: "/workflows/:workflowId",
  runs: "/runs",
  runReplay: "/runs/:runId",
  tasks: "/tasks",
  browserSessions: "/browser-sessions",
  browserProfiles: "/browser-profiles",
  recordings: "/recordings",
  recordingDetail: "/recordings/:recordingId",
  credentials: "/credentials",
  credentialsOAuthCallback: "/credentials/oauth/callback",
  settings: "/settings",
  members: "/settings/members",
  admin: "/admin",
  adminSection: "/admin/:section",
  notFound: "*",
} as const;

export type RouteKey = keyof typeof ROUTES;

export const routePath = {
  workflows: (): string => ROUTES.workflows,
  workflowDetail: (workflowId: string): string =>
    `/workflows/${workflowId}`,
  runs: (): string => ROUTES.runs,
  runReplay: (runId: string): string => `/runs/${runId}`,
  tasks: (): string => ROUTES.tasks,
  browserSessions: (): string => ROUTES.browserSessions,
  browserProfiles: (): string => ROUTES.browserProfiles,
  recordings: (): string => ROUTES.recordings,
  recordingDetail: (recordingId: string): string =>
    `/recordings/${recordingId}`,
  credentials: (): string => ROUTES.credentials,
  settings: (): string => ROUTES.settings,
  members: (): string => ROUTES.members,
  admin: (): string => ROUTES.admin,
  adminSection: (section: string): string => `/admin/${section}`,
  clientDownload: (): string => ROUTES.clientDownload,
} as const;
