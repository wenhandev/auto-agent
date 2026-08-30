import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Play, Settings, Workflow } from "lucide-react";
import { useDesktopAuth } from "../DesktopAuthContext";
import { friendlyEnvStatus } from "../deviceStatus";
import { useRuntimeConnectionStatus } from "../useRuntimeConnectionStatus";
import {
  isUserSaid,
  send,
  start,
  type ConversationView,
} from "../agent/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export function HomePage() {
  const { t } = useTranslation();
  const { session } = useDesktopAuth();
  const { status, connected: online, loggedIn } = useRuntimeConnectionStatus();
  const [view, setView] = useState<ConversationView | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const envStatus = status?.preflight.environment_status ?? "unknown";
  const signedInToWorker = loggedIn || !!session;
  const displayName =
    session?.displayName?.trim() || t("desktop.home.welcomeFallback");

  useEffect(() => {
    let cancelled = false;
    start()
      .then((opened) => {
        if (!cancelled) setView(opened);
      })
      .catch(() => {
        if (!cancelled) setError(t("desktop.home.agentError"));
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!view || !text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await send(view.id, text, crypto.randomUUID());
      setView(next);
      setDraft("");
    } catch {
      setError(t("desktop.home.agentError"));
    } finally {
      setBusy(false);
    }
  }

  const userEvents = view?.events.filter(isUserSaid) ?? [];
  const queued =
    view?.next.kind === "dispatch" ? view.next.objective : null;

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {t("desktop.home.welcome", { name: displayName })}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("desktop.home.subtitle")}
        </p>
      </div>

      <div className="flex min-h-[20rem] flex-1 flex-col gap-3">
        <div className="flex flex-1 flex-col gap-2 overflow-auto rounded-md border bg-card p-4">
          {userEvents.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("desktop.home.agentEmpty")}
            </p>
          ) : (
            userEvents.map((event) => (
              <p key={event.seq} className="whitespace-pre-wrap text-sm">
                {event.text}
              </p>
            ))
          )}
          {queued && (
            <p className="text-sm text-muted-foreground">
              {t("desktop.home.agentQueued", { objective: queued })}
            </p>
          )}
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-2">
          <Label htmlFor="home-agent-composer">
            {t("desktop.home.agentComposerLabel")}
          </Label>
          <Textarea
            id="home-agent-composer"
            value={draft}
            onChange={(change) => setDraft(change.target.value)}
            placeholder={t("desktop.home.agentPlaceholder")}
            rows={3}
            maxLength={8000}
            disabled={!view || busy}
          />
          <div className="flex items-center justify-between gap-3">
            {error ? (
              <p className="text-sm text-destructive">{error}</p>
            ) : (
              <span />
            )}
            <Button type="submit" disabled={!view || busy || !draft.trim()}>
              {t("desktop.home.agentSend")}
            </Button>
          </div>
        </form>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Button asChild variant="ghost" size="sm" className="h-8 px-2">
          <Link to="/runs">
            <Play className="mr-1 h-3.5 w-3.5" />
            {t("desktop.home.runsCta")}
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="h-8 px-2">
          <Link to="/workflows">
            <Workflow className="mr-1 h-3.5 w-3.5" />
            {t("desktop.home.workflowsCta")}
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="h-8 px-2">
          <Link to="/settings">
            <Settings className="mr-1 h-3.5 w-3.5" />
            {t("desktop.home.settingsCta")}
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Badge variant={online ? "default" : "secondary"}>
          {online ? t("desktop.home.online") : t("desktop.home.offline")}
        </Badge>
        <Badge
          variant={
            envStatus === "ready"
              ? "default"
              : envStatus === "not_ready"
                ? "destructive"
                : "outline"
          }
        >
          {friendlyEnvStatus(envStatus)}
        </Badge>
        {!online && (
          <p className="text-muted-foreground">
            {signedInToWorker
              ? t("desktop.home.offlineHintWorkerDisconnected")
              : t("desktop.home.offlineHintNotSignedIn")}
          </p>
        )}
        {online && envStatus === "not_ready" && (
          <p className="text-muted-foreground">{t("desktop.home.setupHint")}</p>
        )}
        <Button asChild variant="link" size="sm" className="h-auto p-0">
          <Link to="/device">{t("desktop.home.viewDeviceStatus")}</Link>
        </Button>
      </div>
    </div>
  );
}
