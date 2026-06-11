import type { Workflow } from "./types";

async function parseError(res: Response): Promise<string> {
  try {
    const text = await res.text();
    return text || `${res.status} ${res.statusText}`;
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

export async function getSampleWorkflow(): Promise<Workflow> {
  const res = await fetch("/api/sample-workflow");
  if (!res.ok) {
    throw new Error(`getSampleWorkflow failed: ${await parseError(res)}`);
  }
  return (await res.json()) as Workflow;
}

export async function generateWorkflow(description: string): Promise<Workflow> {
  const res = await fetch("/api/workflow/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  });
  if (!res.ok) {
    throw new Error(`generateWorkflow failed: ${await parseError(res)}`);
  }
  return (await res.json()) as Workflow;
}
