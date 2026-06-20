import { afterEach, describe, expect, it, vi } from "vitest";
import { AutoAgent } from "./client.js";
import { ApiError } from "./http.js";

type MockCall = {
  method: string;
  url: string;
  body?: unknown;
};

function utcNow(): string {
  return new Date().toISOString();
}

function runOut(runId = "run-1", status = "queued") {
  return {
    id: runId,
    workflow_id: "wf-1",
    workflow_version_id: "wv-1",
    status,
    mode: "graph",
    queued_at: utcNow(),
    started_at: null,
    finished_at: null,
    error: null,
    source: "api",
    trigger_id: null,
    trigger_context: { kind: "api" },
    parameters: null,
    artifact_counts: {},
    browser_profile_id: null,
    totp_identifier: null,
    pending_approval: null,
    queue_position: 1,
  };
}

function replay(runId = "run-1", status = "queued") {
  return {
    run: runOut(runId, status),
    workflow_version: {
      id: "wv-1",
      workflow_id: "wf-1",
      version_index: 1,
      authored_by: "manual",
      workflow: { nodes: [], edges: [], start_id: "start", parameters: [] },
      created_at: utcNow(),
    },
    events: [],
  };
}

function createMockFetch() {
  const calls: MockCall[] = [];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });

    const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
    if (auth !== "Bearer sk_test_key") {
      return new Response(JSON.stringify({ detail: "unauthorized" }), { status: 401 });
    }

    const path = new URL(url).pathname;
    if (method === "POST" && path === "/api/v1/run-task") {
      expect(body.prompt).toBe("extract title");
      expect(body.url).toBe("https://example.com");
      return new Response(
        JSON.stringify({ run_id: "run-task-1", status: "queued" }),
        { status: 202 },
      );
    }
    if (method === "POST" && path === "/api/v1/workflows/wf-1/run") {
      return new Response(JSON.stringify(runOut("run-wf-1")), { status: 202 });
    }
    if (method === "GET" && path === "/api/v1/runs/run-1") {
      return new Response(JSON.stringify(replay("run-1", "completed")), { status: 200 });
    }
    if (method === "GET" && path === "/api/v1/runs") {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: "run-1",
              workflow_id: "wf-1",
              workflow_name: "demo",
              workflow_version_id: "wv-1",
              version_index: 1,
              status: "completed",
              queued_at: utcNow(),
              started_at: utcNow(),
              finished_at: utcNow(),
              duration_ms: 100,
              error_summary: null,
              pending_approval: null,
              queue_position: null,
            },
          ],
          next_cursor: null,
        }),
        { status: 200 },
      );
    }
    if (method === "POST" && path === "/api/v1/runs/run-1/cancel") {
      return new Response(JSON.stringify(runOut("run-1", "aborted")), { status: 200 });
    }
    if (method === "GET" && path === "/api/v1/workflows") {
      return new Response(
        JSON.stringify([
          {
            id: "wf-1",
            name: "demo",
            description: null,
            current_version_index: 1,
            last_run_status: "completed",
            updated_at: utcNow(),
          },
        ]),
        { status: 200 },
      );
    }

    return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
  });

  return { fetchMock, calls };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AutoAgent", () => {
  it("runTask sends bearer auth and returns typed response", async () => {
    const { fetchMock, calls } = createMockFetch();
    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    const result = await client.runTask({
      prompt: "extract title",
      url: "https://example.com",
    });

    expect(result.run_id).toBe("run-task-1");
    expect(result.status).toBe("queued");
    expect(calls[0]?.method).toBe("POST");
    expect(calls[0]?.url).toBe("http://localhost:8000/api/v1/run-task");
  });

  it("runWorkflow returns typed run", async () => {
    const { fetchMock } = createMockFetch();
    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    const run = await client.runWorkflow("wf-1", { parameters: { x: 1 } });
    expect(run.id).toBe("run-wf-1");
    expect(run.status).toBe("queued");
  });

  it("getRun returns replay payload", async () => {
    const { fetchMock } = createMockFetch();
    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    const replayResponse = await client.getRun("run-1");
    expect(replayResponse.run.status).toBe("completed");
    expect(replayResponse.workflow_version.version_index).toBe(1);
  });

  it("listRuns returns paginated items", async () => {
    const { fetchMock } = createMockFetch();
    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    const page = await client.listRuns({ workflowId: "wf-1", limit: 10 });
    expect(page.items).toHaveLength(1);
    expect(page.items[0]?.workflow_name).toBe("demo");
  });

  it("cancelRun returns aborted run", async () => {
    const { fetchMock } = createMockFetch();
    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    const run = await client.cancelRun("run-1");
    expect(run.status).toBe("aborted");
  });

  it("waitForRun polls until terminal status", async () => {
    const statuses = ["queued", "running", "completed"];
    let index = 0;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const path = new URL(url).pathname;
      if ((init?.method ?? "GET") === "GET" && path === "/api/v1/runs/run-1") {
        const status = statuses[index] ?? "completed";
        index += 1;
        return new Response(JSON.stringify(replay("run-1", status)), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    });

    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    const result = await client.waitForRun("run-1", {
      pollInterval: 1,
      maxInterval: 2,
      timeout: 5_000,
    });

    expect(result.run.status).toBe("completed");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("workflows.list returns workflow items", async () => {
    const { fetchMock } = createMockFetch();
    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    const workflows = await client.workflows.list();
    expect(workflows[0]?.name).toBe("demo");
  });

  it("throws ApiError on non-success responses", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ detail: "rate limited" }), { status: 429 }),
    );

    const client = new AutoAgent({
      baseUrl: "http://localhost:8000",
      apiKey: "sk_test_key",
      fetch: fetchMock,
    });

    await expect(client.listRuns()).rejects.toBeInstanceOf(ApiError);
    await expect(client.listRuns()).rejects.toMatchObject({
      statusCode: 429,
      detail: "rate limited",
    });
  });
});
