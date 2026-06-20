export class ApiError extends Error {
  readonly statusCode: number;
  readonly detail: unknown;

  constructor(statusCode: number, detail: unknown) {
    super(`API error ${statusCode}: ${formatDetail(detail)}`);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

export function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

export type FetchFn = typeof fetch;

export interface HttpTransportOptions {
  baseUrl: string;
  apiKey: string;
  timeout?: number;
  fetch?: FetchFn;
}

export class HttpTransport {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly timeout: number;
  private readonly fetchFn: FetchFn;

  constructor(options: HttpTransportOptions) {
    this.baseUrl = normalizeBaseUrl(options.baseUrl);
    this.apiKey = options.apiKey;
    this.timeout = options.timeout ?? 30_000;
    this.fetchFn = options.fetch ?? fetch;
  }

  async request<T>(
    method: string,
    path: string,
    options?: {
      json?: unknown;
      params?: Record<string, string | number | boolean | undefined>;
    },
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    if (options?.params) {
      for (const [key, value] of Object.entries(options.params)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await this.fetchFn(url, {
        method,
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          ...(options?.json !== undefined
            ? { "Content-Type": "application/json" }
            : {}),
        },
        body: options?.json !== undefined ? JSON.stringify(options.json) : undefined,
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail: unknown;
        try {
          const body = (await response.json()) as { detail?: unknown };
          detail = body.detail ?? body;
        } catch {
          detail = await response.text();
        }
        throw new ApiError(response.status, detail);
      }

      if (response.status === 204) {
        return undefined as T;
      }

      return (await response.json()) as T;
    } finally {
      clearTimeout(timeoutId);
    }
  }
}
