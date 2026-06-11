import { apiClient } from "../api-platform";
import type {
  ChatMessageOut,
  ChatTurnResponse,
} from "../types-platform";

export interface ChatTransport {
  fetchHistory(workflowId: string): Promise<ChatMessageOut[]>;
  sendMessage(workflowId: string, content: string): Promise<ChatTurnResponse>;
}

async function resolveSessionId(workflowId: string): Promise<string> {
  const wf = await apiClient.workflows.get(workflowId);
  if (!wf.chat_session_id) {
    throw new Error("\u5de5\u4f5c\u6d41\u5c1a\u672a\u521b\u5efa\u4f1a\u8bdd");
  }
  return wf.chat_session_id;
}

export const defaultChatTransport: ChatTransport = {
  async fetchHistory(workflowId) {
    const sessionId = await resolveSessionId(workflowId);
    return apiClient.chat.getHistory(sessionId);
  },
  async sendMessage(workflowId, content) {
    const sessionId = await resolveSessionId(workflowId);
    return apiClient.chat.postMessage(sessionId, { message: content });
  },
};

let currentTransport: ChatTransport = defaultChatTransport;

export function setChatTransport(transport: ChatTransport): void {
  currentTransport = transport;
}

export function resetChatTransport(): void {
  currentTransport = defaultChatTransport;
}

export function getChatTransport(): ChatTransport {
  return currentTransport;
}

export function normalizeChatError(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err);
  } catch {
    return "\u672a\u77e5\u9519\u8bef";
  }
}
