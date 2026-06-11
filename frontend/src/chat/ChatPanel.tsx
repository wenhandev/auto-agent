import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";
import type { Workflow, WorkflowVersionOut } from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { getChatTransport, normalizeChatError } from "./api";
import { PatchPreview } from "./PatchPreview";
import { useChatReducer, type ChatMessage } from "./useChatReducer";

interface Props {
  workflowId: string;
  onWorkflowUpdated: (nextVersion: WorkflowVersionOut) => void;
}

function makeLocalId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function ChatPanel({ workflowId, onWorkflowUpdated }: Props) {
  const { t } = useTranslation();
  const {
    state,
    appendUser,
    appendAssistant,
    setStreaming,
    setError,
    setMessages,
  } = useChatReducer();
  const [input, setInput] = useState("");
  const [currentWorkflow, setCurrentWorkflow] = useState<Workflow | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const streamingRef = useRef(state.isStreaming);
  streamingRef.current = state.isStreaming;
  const workflowRef = useRef<Workflow | null>(currentWorkflow);
  workflowRef.current = currentWorkflow;

  const examplePrompts = useMemo(
    () => [
      t("chat.examples.extractTitle"),
      t("chat.examples.addWait"),
      t("chat.examples.changeClick"),
    ],
    [t],
  );

  useEffect(() => {
    let cancelled = false;
    setMessages([]);
    setCurrentWorkflow(null);
    (async () => {
      try {
        const history = await getChatTransport().fetchHistory(workflowId);
        if (cancelled) return;
        const mapped: ChatMessage[] = history.map((m) => ({ ...m }));
        setMessages(mapped);
      } catch (err) {
        if (!cancelled) setError(normalizeChatError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workflowId, setMessages, setError]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.messages, state.isStreaming]);

  const send = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || streamingRef.current) return;

      const userMsg: ChatMessage = {
        id: makeLocalId("user"),
        session_id: "",
        role: "user",
        content: trimmed,
        workflow_version_id: null,
        created_at: new Date().toISOString(),
      };
      appendUser(userMsg);
      setInput("");
      setStreaming(true);
      setError(null);

      const priorWorkflow = workflowRef.current;
      try {
        const resp = await getChatTransport().sendMessage(workflowId, trimmed);
        const wfAfter = resp.new_version?.workflow ?? null;
        const isFullReplace = resp.patch == null && wfAfter != null;
        const patchFailed = resp.patch != null && resp.new_version == null;

        const reference = isFullReplace ? wfAfter : priorWorkflow;
        const assistant: ChatMessage = {
          ...resp.assistant_message,
          patch: resp.patch,
          referenceWorkflow: reference,
          hasError: patchFailed,
          retryUserContent: patchFailed ? trimmed : undefined,
        };
        appendAssistant(assistant);

        if (resp.new_version) {
          setCurrentWorkflow(resp.new_version.workflow);
          onWorkflowUpdated(resp.new_version);
        }
      } catch (err) {
        const errMsg = normalizeChatError(err);
        const assistant: ChatMessage = {
          id: makeLocalId("err"),
          session_id: "",
          role: "assistant",
          content: errMsg,
          workflow_version_id: null,
          created_at: new Date().toISOString(),
          hasError: true,
          retryUserContent: trimmed,
        };
        appendAssistant(assistant);
        setError(errMsg);
      } finally {
        setStreaming(false);
      }
    },
    [
      workflowId,
      appendUser,
      appendAssistant,
      setStreaming,
      setError,
      onWorkflowUpdated,
    ],
  );

  function onKeyDown(e: ReactKeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send(input);
    }
  }

  function onExampleClick(text: string): void {
    setInput(text);
    textareaRef.current?.focus();
  }

  const showEmpty = state.messages.length === 0 && !state.isStreaming;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        ref={scrollRef}
        className="scrollbar-thin flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4"
      >
        {showEmpty && (
          <div className="flex flex-col items-center gap-3 rounded-md border border-dashed p-4 text-center">
            <div className="text-sm font-medium text-foreground">
              {t("chat.emptyTitle")}
            </div>
            <div className="text-xs text-muted-foreground">
              {t("chat.emptyHint")}
            </div>
            <div className="flex w-full flex-col gap-1.5">
              {examplePrompts.map((p) => (
                <button
                  key={p}
                  type="button"
                  className="rounded-md border bg-muted/40 px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                  onClick={() => onExampleClick(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}
        {state.messages.map((m) => (
          <MessageRow
            key={m.id}
            message={m}
            onRetry={() => {
              if (m.retryUserContent) void send(m.retryUserContent);
            }}
          />
        ))}
        {state.isStreaming && (
          <div className="flex justify-start">
            <div className="max-w-[85%] animate-pulse rounded-2xl rounded-bl-sm border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
              {t("chat.streaming")}
            </div>
          </div>
        )}
        {state.error && !state.isStreaming && (
          <div className="text-xs text-destructive">{state.error}</div>
        )}
      </div>
      <div className="flex items-end gap-2 border-t bg-card/40 p-3">
        <Textarea
          ref={textareaRef}
          placeholder={t("chat.placeholder")}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={3}
          disabled={state.isStreaming}
          className="min-h-[64px] flex-1 resize-none"
        />
        <Button
          type="button"
          size="icon"
          onClick={() => void send(input)}
          disabled={state.isStreaming || !input.trim()}
          aria-label={t("chat.send")}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

interface MessageRowProps {
  message: ChatMessage;
  onRetry: () => void;
}

function MessageRow({ message, onRetry }: MessageRowProps) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const hasPatchPreview =
    !isUser && (message.patch != null || message.referenceWorkflow != null);

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl border px-3 py-2 text-sm",
          isUser
            ? "rounded-br-sm bg-primary text-primary-foreground"
            : "rounded-bl-sm bg-muted/40 text-foreground",
          message.hasError && "border-destructive/50",
        )}
      >
        <div className="whitespace-pre-wrap leading-relaxed">
          {message.content}
        </div>
        {hasPatchPreview && (
          <PatchPreview
            patch={message.patch ?? null}
            fullWorkflow={message.referenceWorkflow ?? undefined}
          />
        )}
        {message.hasError && message.retryUserContent && (
          <button
            type="button"
            className="mt-2 text-xs font-medium text-destructive underline-offset-2 hover:underline"
            onClick={onRetry}
          >
            {t("chat.retry")}
          </button>
        )}
      </div>
    </div>
  );
}
