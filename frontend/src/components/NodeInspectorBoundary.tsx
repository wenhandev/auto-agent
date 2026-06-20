import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

function NodeInspectorFallback({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="absolute right-4 top-4 z-30 w-[360px] rounded-lg border border-destructive/40 bg-card p-4 shadow-lg">
      <div className="flex items-start gap-2 text-sm text-destructive">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-2">
          <p className="font-medium">{t("nodeInspector.loadErrorTitle")}</p>
          <p className="text-xs text-muted-foreground">
            {t("nodeInspector.loadErrorHint")}
          </p>
          <Button size="sm" variant="outline" onClick={onClose}>
            {t("nodeInspector.closeAria")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export class NodeInspectorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("NodeInspector render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <NodeInspectorFallback
          onClose={() => {
            this.setState({ error: null });
            useStore.getState().selectNode(null);
          }}
        />
      );
    }
    return this.props.children;
  }
}
