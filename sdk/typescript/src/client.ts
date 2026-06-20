import { HttpTransport } from "./http.js";
import {
  isTerminalStatus,
  runIdFromHandle,
  type RunCreate,
  type RunHandle,
  type RunListPage,
  type RunOut,
  type RunReplayResponse,
  type RunTaskRequest,
  type RunTaskResponse,
} from "./models.js";
import { WorkflowsClient } from "./workflows.js";

export interface AutoAgentOptions {
  baseUrl: string;
  apiKey: string;
  timeout?: number;
  fetch?: typeof fetch;
}

export interface ListRunsOptions {
  workflowId?: string;
  limit?: number;
  cursor?: string;
}

export interface RunWorkflowOptions {
  parameters?: Record<string, unknown>;
  browserProfileId?: string;
  browserSessionId?: string;
  totpIdentifier?: string;
}

export interface WaitForRunOptions {
  timeout?: number;
  pollInterval?: number;
  maxInterval?: number;
}

function omitUndefined<T extends Record<string, unknown>>(value: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(value).filter(([, entry]) => entry !== undefined),
  ) as Partial<T>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toRunCreate(options: RunWorkflowOptions = {}): RunCreate {
  return omitUndefined({
    parameters: options.parameters,
    browser_profile_id: options.browserProfileId,
    browser_session_id: options.browserSessionId,
    totp_identifier: options.totpIdentifier,
  });
}

export class AutoAgent {
  private readonly http: HttpTransport;
  readonly workflows: WorkflowsClient;

  constructor(options: AutoAgentOptions) {
    this.http = new HttpTransport(options);
    this.workflows = new WorkflowsClient(this.http);
  }

  async runTask(request: RunTaskRequest): Promise<RunTaskResponse> {
    const body = omitUndefined({
      prompt: request.prompt,
      url: request.url,
      data_schema: request.data_schema,
      browser_session_id: request.browser_session_id,
      browser_profile_id: request.browser_profile_id,
      totp_identifier: request.totp_identifier,
      max_steps: request.max_steps,
      persist: request.persist,
    });
    return this.http.request<RunTaskResponse>("POST", "/api/v1/run-task", { json: body });
  }

  async runWorkflow(
    workflowId: string,
    options: RunWorkflowOptions = {},
  ): Promise<RunOut> {
    return this.http.request<RunOut>("POST", `/api/v1/workflows/${workflowId}/run`, {
      json: toRunCreate(options),
    });
  }

  async getRun(runId: string): Promise<RunReplayResponse> {
    return this.http.request<RunReplayResponse>("GET", `/api/v1/runs/${runId}`);
  }

  async listRuns(options: ListRunsOptions = {}): Promise<RunListPage> {
    return this.http.request<RunListPage>("GET", "/api/v1/runs", {
      params: {
        workflow_id: options.workflowId,
        limit: options.limit ?? 50,
        cursor: options.cursor,
      },
    });
  }

  async cancelRun(runId: string): Promise<RunOut> {
    return this.http.request<RunOut>("POST", `/api/v1/runs/${runId}/cancel`);
  }

  async waitForRun(
    run: RunHandle,
    options: WaitForRunOptions = {},
  ): Promise<RunReplayResponse> {
    const runId = runIdFromHandle(run);
    const timeout = options.timeout ?? 300_000;
    const pollInterval = options.pollInterval ?? 1_000;
    const maxInterval = options.maxInterval ?? 5_000;
    const deadline = Date.now() + timeout;
    let interval = pollInterval;

    while (true) {
      const replay = await this.getRun(runId);
      if (isTerminalStatus(replay.run.status)) {
        return replay;
      }
      if (Date.now() >= deadline) {
        throw new Error(
          `run ${runId} did not reach terminal status within ${timeout}ms`,
        );
      }
      await sleep(interval);
      interval = Math.min(interval * 1.5, maxInterval);
    }
  }
}
