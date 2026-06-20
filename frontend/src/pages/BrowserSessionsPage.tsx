import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Globe, Plus, RefreshCw, Trash2, XCircle, Brain } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import type { BrowserSessionMemoryEntry, BrowserSessionOut } from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const QK_SESSIONS = ["browser-sessions", "list"] as const;
const QK_PROFILES = ["browser-profiles"] as const;

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function sessionBadgeVariant(
  status: BrowserSessionOut["status"],
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "live":
      return "default";
    case "idle":
      return "secondary";
    case "expired":
      return "destructive";
    default:
      return "outline";
  }
}

export function BrowserSessionsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [memorySessionId, setMemorySessionId] = useState<string | null>(null);
  const [memoryEntries, setMemoryEntries] = useState<BrowserSessionMemoryEntry[]>([]);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [profileId, setProfileId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const sessionsQuery = useQuery({
    queryKey: QK_SESSIONS,
    queryFn: () => apiClient.browserSessions.list(),
    refetchInterval: 15_000,
  });

  const profilesQuery = useQuery({
    queryKey: QK_PROFILES,
    queryFn: () => apiClient.browserProfiles.list(),
  });

  const createMut = useMutation({
    mutationFn: () =>
      apiClient.browserSessions.create(
        profileId ? { profile_id: profileId } : {},
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_SESSIONS });
      setCreateOpen(false);
      setProfileId("");
      setError(null);
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
          : err instanceof Error
            ? err.message
            : String(err);
      setError(message);
    },
  });

  const closeMut = useMutation({
    mutationFn: (sessionId: string) => apiClient.browserSessions.close(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_SESSIONS });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (sessionId: string) => apiClient.browserSessions.remove(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_SESSIONS });
    },
  });

  const keepAliveMut = useMutation({
    mutationFn: (sessionId: string) =>
      apiClient.browserSessions.keepAlive(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_SESSIONS });
    },
  });

  const profiles = profilesQuery.data ?? [];
  const profileNameById = new Map(profiles.map((p) => [p.id, p.name]));
  const sessions = sessionsQuery.data ?? [];

  function onDelete(session: BrowserSessionOut) {
    if (
      !window.confirm(
        t("browserSessions.confirmDelete", { id: session.id.slice(0, 8) }),
      )
    ) {
      return;
    }
    deleteMut.mutate(session.id);
  }

  async function openMemory(session: BrowserSessionOut) {
    setMemorySessionId(session.id);
    setMemoryOpen(true);
    setMemoryLoading(true);
    try {
      const data = await apiClient.browserSessions.getMemory(session.id);
      setMemoryEntries(data.entries ?? []);
    } catch {
      setMemoryEntries([]);
    } finally {
      setMemoryLoading(false);
    }
  }

  async function clearMemory() {
    if (!memorySessionId) return;
    setMemoryLoading(true);
    try {
      const data = await apiClient.browserSessions.clearMemory(memorySessionId);
      setMemoryEntries(data.entries ?? []);
    } finally {
      setMemoryLoading(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="flex items-center justify-between border-b bg-card/40 px-6 py-4">
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5 text-primary" />
          <div>
            <h1 className="text-lg font-semibold">
              {t("browserSessions.title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t("browserSessions.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void sessionsQuery.refetch()}
            disabled={sessionsQuery.isFetching}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            {t("browserSessions.refresh")}
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {t("browserSessions.newSession")}
          </Button>
        </div>
      </div>

      <div className="p-6">
        {sessionsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : sessions.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm font-medium">{t("browserSessions.empty")}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("browserSessions.emptyHint")}
            </p>
            <Button className="mt-4" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              {t("browserSessions.newSession")}
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("browserSessions.table.id")}</TableHead>
                <TableHead>{t("browserSessions.table.profile")}</TableHead>
                <TableHead>{t("browserSessions.table.status")}</TableHead>
                <TableHead>{t("browserSessions.table.started")}</TableHead>
                <TableHead>{t("browserSessions.table.expires")}</TableHead>
                <TableHead className="text-right">
                  {t("browserSessions.table.actions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.map((session) => (
                <TableRow key={session.id}>
                  <TableCell className="font-mono text-xs">
                    {session.id.slice(0, 8)}…
                  </TableCell>
                  <TableCell>
                    {session.profile_id
                      ? profileNameById.get(session.profile_id) ??
                        session.profile_id.slice(0, 8)
                      : t("browserSessions.noProfile")}
                  </TableCell>
                  <TableCell>
                    <Badge variant={sessionBadgeVariant(session.status)}>
                      {t(`browserSessions.status.${session.status}`)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTime(session.started_at)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {session.seconds_until_expiry != null
                      ? t("browserSessions.expiresIn", {
                          seconds: session.seconds_until_expiry,
                        })
                      : formatTime(session.expires_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      {session.status === "live" && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => keepAliveMut.mutate(session.id)}
                            disabled={keepAliveMut.isPending}
                          >
                            {t("browserSessions.keepAlive")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => closeMut.mutate(session.id)}
                            disabled={closeMut.isPending}
                          >
                            <XCircle className="mr-1 h-3.5 w-3.5" />
                            {t("browserSessions.close")}
                          </Button>
                        </>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void openMemory(session)}
                      >
                        <Brain className="mr-1 h-3.5 w-3.5" />
                        {t("browserSessions.memory")}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onDelete(session)}
                        disabled={deleteMut.isPending}
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" />
                        {t("browserSessions.delete")}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("browserSessions.createTitle")}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            {profiles.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label>{t("browserSessions.profileLabel")}</Label>
                <Select
                  value={profileId || "__none__"}
                  onValueChange={(v) =>
                    setProfileId(v === "__none__" ? "" : v)
                  }
                >
                  <SelectTrigger>
                    <SelectValue
                      placeholder={t("browserSessions.profileNone")}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">
                      {t("browserSessions.profileNone")}
                    </SelectItem>
                    {profiles.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => createMut.mutate()}
              disabled={createMut.isPending}
            >
              {createMut.isPending
                ? t("browserSessions.creating")
                : t("browserSessions.createCta")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={memoryOpen} onOpenChange={setMemoryOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("browserSessions.memoryTitle")}</DialogTitle>
          </DialogHeader>
          {memoryLoading ? (
            <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
          ) : memoryEntries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("browserSessions.memoryEmpty")}
            </p>
          ) : (
            <ul className="max-h-64 space-y-2 overflow-auto text-sm">
              {memoryEntries.map((entry, idx) => (
                <li key={idx} className="rounded border p-2">
                  <p className="font-medium">{entry.objective ?? "—"}</p>
                  <p className="text-muted-foreground">{entry.summary}</p>
                </li>
              ))}
            </ul>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setMemoryOpen(false)}>
              {t("common.close")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => void clearMemory()}
              disabled={memoryLoading || memoryEntries.length === 0}
            >
              {t("browserSessions.memoryClear")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
