export const ROUTES = {
  root: "/",
  workflows: "/workflows",
  workflowDetail: "/workflows/:workflowId",
  runs: "/runs",
  runReplay: "/runs/:runId",
  credentials: "/credentials",
  settings: "/settings",
  notFound: "*",
} as const;

export type RouteKey = keyof typeof ROUTES;

export const routePath = {
  workflows: (): string => ROUTES.workflows,
  workflowDetail: (workflowId: string): string =>
    `/workflows/${workflowId}`,
  runs: (): string => ROUTES.runs,
  runReplay: (runId: string): string => `/runs/${runId}`,
  credentials: (): string => ROUTES.credentials,
  settings: (): string => ROUTES.settings,
} as const;
