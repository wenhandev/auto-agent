import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Circle, Plus, Square } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import type { RecordingCreate, RecordingOut } from "@/types-platform";
import { routePath } from "@/routes";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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

const QK_LIST = ["recordings", "list"] as const;
const QK_PROFILES = ["browser-profiles"] as const;

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function statusVariant(
  status: RecordingOut["status"],
): "default" | "secondary" | "outline" {
  switch (status) {
    case "active":
      return "default";
    case "synthesized":
      return "secondary";
    default:
      return "outline";
  }
}

export function RecordingsListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [startUrl, setStartUrl] = useState("");
  const [profileId, setProfileId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: () => apiClient.recordings.list(),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.some((r) => r.status === "active");
      return hasActive ? 5000 : false;
    },
  });

  const profilesQuery = useQuery({
    queryKey: QK_PROFILES,
    queryFn: () => apiClient.browserProfiles.list(),
    enabled: createOpen,
  });

  const createMut = useMutation({
    mutationFn: (body: RecordingCreate) => apiClient.recordings.create(body),
    onSuccess: (recording) => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
      setCreateOpen(false);
      setName("");
      setStartUrl("");
      setProfileId("");
      setError(null);
      navigate(routePath.recordingDetail(recording.id));
    },
    onError: (err: unknown) => {
      setError(formatError(err));
    },
  });

  const stopMut = useMutation({
    mutationFn: (recordingId: string) => apiClient.recordings.stop(recordingId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
    },
  });

  const recordings = listQuery.data ?? [];
  const profiles = profilesQuery.data ?? [];

  function formatError(err: unknown): string {
    return err instanceof ApiError
      ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
      : err instanceof Error
        ? err.message
        : String(err);
  }

  function onCreate() {
    const body: RecordingCreate = {};
    if (name.trim()) body.name = name.trim();
    if (startUrl.trim()) body.start_url = startUrl.trim();
    if (profileId) body.browser_profile_id = profileId;
    createMut.mutate(body);
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="flex items-center justify-between border-b bg-card/40 px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold">{t("recordings.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("recordings.subtitle")}
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          {t("recordings.startRecording")}
        </Button>
      </div>

      <div className="p-6">
        {listQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : recordings.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm font-medium">{t("recordings.empty")}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("recordings.emptyHint")}
            </p>
            <Button className="mt-4" size="sm" onClick={() => setCreateOpen(true)}>
              <Circle className="mr-1.5 h-3.5 w-3.5" />
              {t("recordings.startRecording")}
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("recordings.table.name")}</TableHead>
                <TableHead>{t("recordings.table.status")}</TableHead>
                <TableHead>{t("recordings.table.events")}</TableHead>
                <TableHead>{t("recordings.table.started")}</TableHead>
                <TableHead className="text-right">
                  {t("recordings.table.actions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recordings.map((recording) => (
                <TableRow
                  key={recording.id}
                  className="cursor-pointer"
                  onClick={() =>
                    navigate(routePath.recordingDetail(recording.id))
                  }
                >
                  <TableCell>
                    <div className="font-medium">
                      {recording.name || recording.id.slice(0, 8)}
                    </div>
                    {recording.start_url && (
                      <div className="truncate text-xs text-muted-foreground">
                        {recording.start_url}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(recording.status)}>
                      {t(`recordings.status.${recording.status}`)}
                    </Badge>
                  </TableCell>
                  <TableCell>{recording.event_count}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTime(recording.started_at)}
                  </TableCell>
                  <TableCell
                    className="text-right"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {recording.status === "active" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => stopMut.mutate(recording.id)}
                        disabled={stopMut.isPending}
                      >
                        <Square className="mr-1 h-3.5 w-3.5" />
                        {t("recordings.stop")}
                      </Button>
                    )}
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
            <DialogTitle>{t("recordings.createTitle")}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>{t("recordings.nameLabel")}</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("recordings.namePlaceholder")}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>{t("recordings.startUrlLabel")}</Label>
              <Input
                value={startUrl}
                onChange={(e) => setStartUrl(e.target.value)}
                placeholder={t("recordings.startUrlPlaceholder")}
              />
            </div>
            {profiles.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label>{t("recordings.profileLabel")}</Label>
                <Select
                  value={profileId || "__none__"}
                  onValueChange={(v) =>
                    setProfileId(v === "__none__" ? "" : v)
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t("recordings.profileNone")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">
                      {t("recordings.profileNone")}
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
              onClick={onCreate}
              disabled={createMut.isPending}
            >
              {createMut.isPending
                ? t("recordings.starting")
                : t("recordings.startRecording")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
