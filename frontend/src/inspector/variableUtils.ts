import type { WorkflowEdge } from "@/types";

export const TOKEN_RE = /\{\{\s*([^{}]+?)\s*\}\}/g;

export type TokenSegment =
  | { type: "text"; value: string }
  | { type: "token"; raw: string; inner: string };

export function parseTokenSegments(value: string): TokenSegment[] {
  const segments: TokenSegment[] = [];
  let lastIndex = 0;
  const re = new RegExp(TOKEN_RE.source, "g");
  let match: RegExpExecArray | null;
  while ((match = re.exec(value)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        value: value.slice(lastIndex, match.index),
      });
    }
    segments.push({
      type: "token",
      raw: match[0],
      inner: match[1].trim(),
    });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < value.length) {
    segments.push({ type: "text", value: value.slice(lastIndex) });
  }
  if (segments.length === 0) {
    segments.push({ type: "text", value: "" });
  }
  return segments;
}

export function segmentsToValue(segments: TokenSegment[]): string {
  return segments.map((s) => (s.type === "text" ? s.value : s.raw)).join("");
}

export function removeToken(value: string, tokenRaw: string): string {
  return value.replace(tokenRaw, "");
}

export function isChipToken(inner: string): boolean {
  const prefix = inner.split(".", 1)[0];
  return prefix === "nodes" || prefix === "cred";
}

export function getPredecessorIds(
  nodeId: string,
  edges: WorkflowEdge[],
): Set<string> {
  const reverse = new Map<string, string[]>();
  for (const edge of edges) {
    const list = reverse.get(edge.target) ?? [];
    list.push(edge.source);
    reverse.set(edge.target, list);
  }

  const seen = new Set<string>();
  const queue = [...(reverse.get(nodeId) ?? [])];
  while (queue.length > 0) {
    const id = queue.shift()!;
    if (seen.has(id)) continue;
    seen.add(id);
    for (const pred of reverse.get(id) ?? []) {
      if (!seen.has(pred)) queue.push(pred);
    }
  }
  return seen;
}

export interface ShapeTreeNode {
  path: string;
  label: string;
  preview: string;
  children?: ShapeTreeNode[];
}

export function truncatePreview(value: unknown, max = 80): string {
  let text: string;
  if (value === null) text = "null";
  else if (value === undefined) text = "";
  else if (typeof value === "string") text = value;
  else {
    try {
      text = JSON.stringify(value);
    } catch {
      text = String(value);
    }
  }
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function buildShapeChildren(
  value: unknown,
  pathPrefix: string,
): ShapeTreeNode[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      const path = `${pathPrefix}.${index}`;
      const childPath = path.slice("output.".length);
      if (item !== null && typeof item === "object") {
        return {
          path: childPath,
          label: String(index),
          preview: truncatePreview(item),
          children: buildShapeChildren(item, path),
        };
      }
      return {
        path: childPath,
        label: String(index),
        preview: truncatePreview(item),
      };
    });
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).map(
      ([key, child]) => {
        const path = `${pathPrefix}.${key}`;
        const childPath = path.slice("output.".length);
        if (child !== null && typeof child === "object") {
          return {
            path: childPath,
            label: key,
            preview: truncatePreview(child),
            children: buildShapeChildren(child, path),
          };
        }
        return {
          path: childPath,
          label: key,
          preview: truncatePreview(child),
        };
      },
    );
  }
  return [];
}

export function buildOutputShapeTree(output: unknown): ShapeTreeNode[] {
  return buildShapeChildren(output, "output");
}

export function tokenForPath(nodeId: string, dotPath: string): string {
  return `{{nodes.${nodeId}.output.${dotPath}}}`;
}

function navigateValue(root: unknown, segments: string[]): unknown {
  let cur: unknown = root;
  for (const seg of segments) {
    if (cur === null || cur === undefined) return undefined;
    if (Array.isArray(cur)) {
      const idx = Number.parseInt(seg, 10);
      if (Number.isNaN(idx) || idx < 0 || idx >= cur.length) return undefined;
      cur = cur[idx];
      continue;
    }
    if (typeof cur === "object") {
      cur = (cur as Record<string, unknown>)[seg];
      continue;
    }
    return undefined;
  }
  return cur;
}

export function resolveTokenPreview(
  inner: string,
  shapes: Record<string, unknown>,
): string | null {
  const parts = inner.split(".");
  if (parts[0] === "cred") {
    return null;
  }
  if (parts[0] !== "nodes" || parts.length < 2) {
    return null;
  }
  const nodeId = parts[1];
  const shape = shapes[nodeId];
  if (shape === undefined) return null;

  if (parts.length === 2) {
    return truncatePreview(shape, 200);
  }

  const root = parts[2];
  const rest = parts.slice(3);

  if (root === "output") {
    const resolved = navigateValue(shape, rest);
    return resolved === undefined ? null : truncatePreview(resolved, 200);
  }

  return null;
}

export function insertAtSelection(
  value: string,
  token: string,
  selectionStart: number,
  selectionEnd: number,
): { value: string; cursor: number } {
  const start = selectionStart;
  const end = selectionEnd;
  const next = value.slice(0, start) + token + value.slice(end);
  return { value: next, cursor: start + token.length };
}
