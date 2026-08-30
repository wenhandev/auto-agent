import { Workflow } from "lucide-react";

interface DesktopSplashProps {
  message?: string;
  detail?: string;
}

export function DesktopSplash({ message = "Starting…", detail }: DesktopSplashProps) {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center bg-background px-6 text-center"
      style={{ backgroundColor: "#0a0a0a", color: "#fafafa" }}
    >
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <Workflow className="h-6 w-6" />
      </div>
      <h1 className="text-lg font-semibold tracking-tight">Auto Agent</h1>
      <p className="mt-2 text-sm text-muted-foreground">{message}</p>
      {detail ? (
        <p className="mt-1 max-w-sm text-xs text-muted-foreground/80">{detail}</p>
      ) : null}
    </div>
  );
}
