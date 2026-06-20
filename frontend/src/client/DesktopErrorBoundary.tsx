import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class DesktopErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[DesktopErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="flex min-h-screen items-center justify-center p-6 text-center"
          style={{ backgroundColor: "#0a0a0a", color: "#fafafa" }}
        >
          <div className="max-w-md space-y-4">
            <p className="text-lg font-medium">Something went wrong</p>
            <p className="text-sm opacity-80">{this.state.error.message}</p>
            <Button
              type="button"
              onClick={() => {
                this.setState({ error: null });
                window.location.reload();
              }}
            >
              Reload app
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
