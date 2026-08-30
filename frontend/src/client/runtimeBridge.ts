import { isTauriShell } from "./tauriShell";

const DEV_RUNTIME_BASE = "http://127.0.0.1:3921";

async function bodyToString(body: RequestInit["body"]): Promise<string | undefined> {
  if (body == null) return undefined;
  if (typeof body === "string") return body;
  if (body instanceof URLSearchParams) return body.toString();
  if (body instanceof ArrayBuffer) return new TextDecoder().decode(body);
  if (ArrayBuffer.isView(body)) {
    return new TextDecoder().decode(body.buffer);
  }
  if (body instanceof Blob) return body.text();
  return undefined;
}

/** Monolith bridge: UI → Tauri invoke → embedded runtime (no WebView → localhost). */
export async function runtimeFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  if (!isTauriShell()) {
    return fetch(`${DEV_RUNTIME_BASE}${normalizedPath}`, init);
  }

  const headers: Record<string, string> = {};
  if (init?.headers) {
    const headerBag = new Headers(init.headers);
    headerBag.forEach((value, key) => {
      headers[key] = value;
    });
  }

  const { invoke } = await import("@tauri-apps/api/core");
  const result = await invoke<{ status: number; body: string }>("runtime_invoke", {
    request: {
      method: (init?.method || "GET").toUpperCase(),
      path: normalizedPath,
      body: await bodyToString(init?.body),
      headers: Object.keys(headers).length > 0 ? headers : undefined,
    },
  });

  return new Response(result.body, {
    status: result.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function fetchRuntimeHealth(): Promise<boolean> {
  if (!isTauriShell()) {
    try {
      const res = await fetch(`${DEV_RUNTIME_BASE}/health`, {
        signal: AbortSignal.timeout(2000),
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { status?: string };
      return data.status === "ok";
    } catch {
      return false;
    }
  }

  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const data = await invoke<{ runtime_ready: boolean }>("runtime_health");
    return data.runtime_ready;
  } catch {
    return false;
  }
}

export async function runtimeStreamUrl(path: string): Promise<string> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!isTauriShell()) {
    return `${DEV_RUNTIME_BASE}${normalizedPath}`;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("runtime_stream_url", { path: normalizedPath });
}

/** Subscribe to local run SSE via Tauri (monolith — no EventSource to localhost). */
export async function subscribeRunEvents(
  runId: string,
  onData: (data: string) => void,
): Promise<() => void> {
  if (!isTauriShell()) {
    const url = await runtimeStreamUrl(`/runs/${encodeURIComponent(runId)}/events`);
    const source = new EventSource(url);
    source.onmessage = (msg) => onData(msg.data);
    return () => source.close();
  }

  const [{ invoke }, { listen }] = await Promise.all([
    import("@tauri-apps/api/core"),
    import("@tauri-apps/api/event"),
  ]);
  const subscriptionId = await invoke<number>("runtime_subscribe_run_events", {
    runId,
  });
  const unlisten = await listen<{ run_id: string; data: string }>(
    "runtime-run-event",
    (event) => {
      if (event.payload.run_id === runId) {
        onData(event.payload.data);
      }
    },
  );
  return async () => {
    unlisten();
    await invoke("runtime_unsubscribe", { subscriptionId });
  };
}

/** Subscribe to live browser stream via Tauri (monolith — no WebSocket from WebView). */
export async function subscribeStreamFrames(
  runId: string,
  onPayload: (payload: Record<string, unknown>) => void,
): Promise<() => void> {
  if (!isTauriShell()) {
    const wsUrl = (await runtimeStreamUrl(`/ws/stream/${encodeURIComponent(runId)}`)).replace(
      /^http/,
      "ws",
    );
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (msg) => {
      try {
        onPayload(JSON.parse(msg.data as string) as Record<string, unknown>);
      } catch {
        // ignore
      }
    };
    return () => ws.close();
  }

  const [{ invoke }, { listen }] = await Promise.all([
    import("@tauri-apps/api/core"),
    import("@tauri-apps/api/event"),
  ]);
  const subscriptionId = await invoke<number>("runtime_subscribe_stream", { runId });
  const unlisten = await listen<{ run_id: string; payload: Record<string, unknown> }>(
    "runtime-stream-frame",
    (event) => {
      if (event.payload.run_id === runId) {
        onPayload(event.payload.payload);
      }
    },
  );
  return async () => {
    unlisten();
    await invoke("runtime_unsubscribe", { subscriptionId });
  };
}
