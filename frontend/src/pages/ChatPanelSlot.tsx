import { Component, lazy, Suspense } from "react";
import type { ComponentType, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { WorkflowVersionOut } from "@/types-platform";

interface ChatPanelProps {
  workflowId: string;
  onWorkflowUpdated: (nextVersion: WorkflowVersionOut) => void;
}

const LazyChatPanel = lazy<ComponentType<ChatPanelProps>>(async () => {
  try {
    const mod = (await import("../chat")) as {
      ChatPanel?: ComponentType<ChatPanelProps>;
      default?: ComponentType<ChatPanelProps>;
    };
    const Component = mod.ChatPanel ?? mod.default;
    if (!Component) {
      throw new Error("ChatPanel module does not export ChatPanel or default");
    }
    return { default: Component };
  } catch (err) {
    return {
      default: function ChatUnavailable() {
        return <ChatPlaceholder fallbackError={err} />;
      },
    };
  }
});

function ChatPlaceholder({
  fallbackError,
}: {
  fallbackError?: unknown;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
      <div>
        <div>{t("pages.workflowDetail.chatPanelLoading")}</div>
        <div className="mt-2 text-[11px] text-muted-foreground/80">
          {(fallbackError as Error | undefined)?.message ??
            t("pages.workflowDetail.chatPanelModuleMissing")}
        </div>
      </div>
    </div>
  );
}

interface ErrorBoundaryState {
  error: Error | null;
}

class ChatErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.warn("ChatPanel error boundary caught", error);
  }

  render() {
    if (this.state.error) {
      return <ChatErrorMessage error={this.state.error} />;
    }
    return this.props.children;
  }
}

function ChatErrorMessage({ error }: { error: Error }) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
      <div>
        <div>{t("pages.workflowDetail.chatPanelNotReady")}</div>
        <div className="mt-2 text-[11px] text-muted-foreground/80">
          {error.message}
        </div>
      </div>
    </div>
  );
}

function ChatFallback() {
  const { t } = useTranslation();
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
      {t("pages.workflowDetail.chatPanelLoading")}
    </div>
  );
}

export function ChatPanelSlot(props: ChatPanelProps) {
  return (
    <ChatErrorBoundary>
      <Suspense fallback={<ChatFallback />}>
        <LazyChatPanel {...props} />
      </Suspense>
    </ChatErrorBoundary>
  );
}
