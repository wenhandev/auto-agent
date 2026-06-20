import { useState } from "react";
import { Navigate } from "react-router-dom";
import { Workflow } from "lucide-react";
import { DesktopApiError } from "../api";
import { useDesktopAuth } from "../DesktopAuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const DEFAULT_CLOUD_URL =
  import.meta.env.VITE_CLOUD_URL || "http://127.0.0.1:8001";

export function DesktopLoginPage() {
  const { session, isLoading, login } = useDesktopAuth();
  const [cloudUrl, setCloudUrl] = useState(DEFAULT_CLOUD_URL);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isLoading && session) {
    if (session.approvalStatus === "pending") {
      return <Navigate to="/pending" replace />;
    }
    if (session.approvalStatus === "rejected") {
      return <Navigate to="/login" replace />;
    }
    return <Navigate to="/" replace />;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ cloudUrl, email, password });
    } catch (err: unknown) {
      const message =
        err instanceof DesktopApiError && err.status === 401
          ? "Invalid email or password."
          : err instanceof DesktopApiError && err.status === 403
            ? "Clients are disabled for this organisation."
            : err instanceof Error
              ? err.message
              : String(err);
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Workflow className="h-5 w-5" />
          </div>
          <CardTitle>Auto Agent Client</CardTitle>
          <CardDescription>
            Sign in with your cloud account to register this device as a worker.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cloud-url">Cloud URL</Label>
              <Input
                id="cloud-url"
                type="url"
                value={cloudUrl}
                onChange={(e) => setCloudUrl(e.target.value)}
                placeholder="https://your-cloud.example.com"
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
