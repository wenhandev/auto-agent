import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Pencil, Plus, Trash2, Download } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import type {
  BrowserProfileCreate,
  BrowserProfileOut,
  BrowserProfileUpdate,
  RunListItem,
} from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const QK_LIST = ["browser-profiles"] as const;
const QK_RUNS = ["runs", "list", "capture"] as const;

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function formatError(err: unknown): string {
  return err instanceof ApiError
    ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
    : err instanceof Error
      ? err.message
      : String(err);
}

interface ProfileModalProps {
  open: boolean;
  editing: BrowserProfileOut | null;
  onClose(): void;
}

function ProfileModal({ open, editing, onClose }: ProfileModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [userAgent, setUserAgent] = useState("");
  const [width, setWidth] = useState("1280");
  const [height, setHeight] = useState("720");
  const [persistCookies, setPersistCookies] = useState(true);
  const [persistLocalStorage, setPersistLocalStorage] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(editing?.name ?? "");
      setUserAgent(editing?.user_agent ?? "");
      setWidth(String(editing?.viewport?.width ?? 1280));
      setHeight(String(editing?.viewport?.height ?? 720));
      setPersistCookies(editing?.persist_cookies ?? true);
      setPersistLocalStorage(editing?.persist_local_storage ?? true);
      setError(null);
    }
  }, [open, editing]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const viewport = {
        width: Number(width) || 1280,
        height: Number(height) || 720,
      };
      if (editing) {
        const body: BrowserProfileUpdate = {
          name: name.trim(),
          user_agent: userAgent.trim() || null,
          viewport,
          persist_cookies: persistCookies,
          persist_local_storage: persistLocalStorage,
        };
        return apiClient.browserProfiles.update(editing.id, body);
      }
      const body: BrowserProfileCreate = {
        name: name.trim(),
        user_agent: userAgent.trim() || null,
        viewport,
        persist_cookies: persistCookies,
        persist_local_storage: persistLocalStorage,
      };
      return apiClient.browserProfiles.create(body);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
      onClose();
    },
    onError: (err: unknown) => setError(formatError(err)),
  });

  function onSubmit() {
    if (!name.trim()) {
      setError(t("browserProfiles.nameRequired"));
      return;
    }
    saveMut.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {editing
              ? t("browserProfiles.editTitle")
              : t("browserProfiles.createTitle")}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>{t("browserProfiles.nameLabel")}</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("browserProfiles.namePlaceholder")}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t("browserProfiles.userAgentLabel")}</Label>
            <Input
              value={userAgent}
              onChange={(e) => setUserAgent(e.target.value)}
              placeholder={t("browserProfiles.userAgentPlaceholder")}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>{t("browserProfiles.widthLabel")}</Label>
              <Input
                type="number"
                min={1}
                value={width}
                onChange={(e) => setWidth(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>{t("browserProfiles.heightLabel")}</Label>
              <Input
                type="number"
                min={1}
                value={height}
                onChange={(e) => setHeight(e.target.value)}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-4 rounded-md border px-3 py-2">
            <Label htmlFor="persist-cookies">
              {t("browserProfiles.persistCookies")}
            </Label>
            <Switch
              id="persist-cookies"
              checked={persistCookies}
              onCheckedChange={setPersistCookies}
            />
          </div>
          <div className="flex items-center justify-between gap-4 rounded-md border px-3 py-2">
            <Label htmlFor="persist-storage">
              {t("browserProfiles.persistLocalStorage")}
            </Label>
            <Switch
              id="persist-storage"
              checked={persistLocalStorage}
              onCheckedChange={setPersistLocalStorage}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={onSubmit} disabled={saveMut.isPending}>
            {saveMut.isPending
              ? t("common.saving")
              : editing
                ? t("common.save")
                : t("common.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface CaptureModalProps {
  open: boolean;
  profile: BrowserProfileOut | null;
  onClose(): void;
}

function CaptureModal({ open, profile, onClose }: CaptureModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const runsQuery = useQuery({
    queryKey: QK_RUNS,
    queryFn: () => apiClient.runs.list(),
    enabled: open,
  });

  useEffect(() => {
    if (open) {
      setRunId("");
      setError(null);
      setSuccess(false);
    }
  }, [open, profile]);

  const runs = (runsQuery.data ?? []).slice().sort((a, b) => {
    const rank = (r: RunListItem) =>
      r.status === "running" ? 0 : r.status === "queued" ? 1 : 2;
    const diff = rank(a) - rank(b);
    if (diff !== 0) return diff;
    return (
      new Date(b.started_at ?? b.queued_at).getTime() -
      new Date(a.started_at ?? a.queued_at).getTime()
    );
  });

  useEffect(() => {
    if (open && runs.length > 0 && !runId) {
      const preferred =
        runs.find((r) => r.status === "running") ??
        runs.find((r) => r.status === "queued") ??
        runs[0];
      if (preferred) setRunId(preferred.id);
    }
  }, [open, runs, runId]);

  const captureMut = useMutation({
    mutationFn: () =>
      apiClient.browserProfiles.captureFromRun(profile!.id, runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
      setSuccess(true);
      setError(null);
    },
    onError: (err: unknown) => setError(formatError(err)),
  });

  function onSubmit() {
    if (!runId) {
      setError(t("browserProfiles.captureSelectRun"));
      return;
    }
    captureMut.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("browserProfiles.captureTitle")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            {t("browserProfiles.captureHint", { name: profile?.name ?? "" })}
          </p>
          {runsQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
          ) : runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("browserProfiles.captureNoRuns")}
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label>{t("browserProfiles.captureRunLabel")}</Label>
              <Select value={runId} onValueChange={setRunId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {runs.map((run) => (
                    <SelectItem key={run.id} value={run.id}>
                      {run.workflow_name} · {run.status} · {run.id.slice(0, 8)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {success && (
            <p className="text-sm text-emerald-500">
              {t("browserProfiles.captureSuccess")}
            </p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {success ? t("common.close") : t("common.cancel")}
          </Button>
          {!success && runs.length > 0 && (
            <Button onClick={onSubmit} disabled={captureMut.isPending}>
              {captureMut.isPending
                ? t("browserProfiles.capturing")
                : t("browserProfiles.captureFromRun")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function BrowserProfilesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<BrowserProfileOut | null>(null);
  const [captureProfile, setCaptureProfile] = useState<BrowserProfileOut | null>(
    null,
  );

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: () => apiClient.browserProfiles.list(),
  });

  const deleteMut = useMutation({
    mutationFn: (profileId: string) => apiClient.browserProfiles.remove(profileId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
    },
  });

  const profiles = listQuery.data ?? [];

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(profile: BrowserProfileOut) {
    setEditing(profile);
    setModalOpen(true);
  }

  function onDelete(profile: BrowserProfileOut) {
    if (!window.confirm(t("browserProfiles.confirmDelete", { name: profile.name }))) {
      return;
    }
    deleteMut.mutate(profile.id);
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="flex items-center justify-between border-b bg-card/40 px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold">{t("browserProfiles.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("browserProfiles.subtitle")}
          </p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          {t("browserProfiles.newProfile")}
        </Button>
      </div>

      <div className="p-6">
        {listQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : profiles.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm font-medium">{t("browserProfiles.empty")}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("browserProfiles.emptyHint")}
            </p>
            <Button className="mt-4" size="sm" onClick={openCreate}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              {t("browserProfiles.newProfile")}
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("browserProfiles.table.name")}</TableHead>
                <TableHead>{t("browserProfiles.table.viewport")}</TableHead>
                <TableHead>{t("browserProfiles.table.storage")}</TableHead>
                <TableHead>{t("browserProfiles.table.updated")}</TableHead>
                <TableHead className="text-right">
                  {t("browserProfiles.table.actions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {profiles.map((profile) => (
                <TableRow key={profile.id}>
                  <TableCell>
                    <div className="font-medium">{profile.name}</div>
                    {profile.has_storage_state && (
                      <Badge variant="secondary" className="mt-1">
                        {t("browserProfiles.hasStorage")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {profile.viewport
                      ? `${profile.viewport.width}×${profile.viewport.height}`
                      : "1280×720"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {[
                      profile.persist_cookies && t("browserProfiles.cookies"),
                      profile.persist_local_storage &&
                        t("browserProfiles.localStorage"),
                    ]
                      .filter(Boolean)
                      .join(", ") || "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTime(profile.updated_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCaptureProfile(profile)}
                      >
                        <Download className="mr-1 h-3.5 w-3.5" />
                        {t("browserProfiles.captureFromRun")}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openEdit(profile)}
                      >
                        <Pencil className="mr-1 h-3.5 w-3.5" />
                        {t("common.edit")}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onDelete(profile)}
                        disabled={deleteMut.isPending}
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" />
                        {t("common.delete")}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <ProfileModal
        open={modalOpen}
        editing={editing}
        onClose={() => setModalOpen(false)}
      />
      <CaptureModal
        open={!!captureProfile}
        profile={captureProfile}
        onClose={() => setCaptureProfile(null)}
      />
    </div>
  );
}
