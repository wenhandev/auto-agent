import type { HttpTransport } from "./http.js";
import type { WorkflowListItem } from "./models.js";

export class WorkflowsClient {
  constructor(private readonly http: HttpTransport) {}

  async list(): Promise<WorkflowListItem[]> {
    return this.http.request<WorkflowListItem[]>("GET", "/api/v1/workflows");
  }

  async get(workflowId: string): Promise<Record<string, unknown>> {
    return this.http.request<Record<string, unknown>>(
      "GET",
      `/api/v1/workflows/${workflowId}`,
    );
  }
}
