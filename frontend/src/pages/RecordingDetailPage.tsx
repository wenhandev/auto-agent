import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Sparkles, Square } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import { routePath } from "@/routes";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const QK_DETAIL = (id: string) => ["recordings", "detail", id] as const;
const QK_LIST = ["recordings", "list"] as const;

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function eventSummary(event: Record<string, unknown>): string {
  const type = String(event.type ?? "event");
  const parts = [type];
  if (typeof event.selector === "string" && event.selector) {
    parts.push(event.selector);
  } else if (typeof event.url === "string" && event.url) {
    parts.push(event.url);
  } else if (typeof event.description === "string" && event.description) {
    parts.push(event.description);
  } else if (typeof event.name === "string" && event.name) {
    parts.push(event.name);
  }
  return parts.join(" · ");
}

export function RecordingDetailPage() {
  const { t } = useTranslation();
  const { recordingId } = useParams<{ recordingId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const detailQuery = useQuery({
    queryKey: QK_DETAIL(recordingId ?? ""),
    queryFn: () => apiClient.recordings.get(recordingId!),
    enabled: !!recordingId,
    refetchInterval: (query) =>
      query.state.data?.status === "active" ? 3000 : false,
  });

  const liveQuery = useQuery({
    queryKey: ["recordings", "live", recordingId ?? ""],
    queryFn: () => apiClient.recordings.liveEvents(recordingId!),
    enabled: detailQuery.data?.status === "active" && !!recordingId,
    refetchInterval: 2000,
  });

  const stopMut = useMutation({
    mutationFn: () => apiClient.recordings.stop(recordingId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: QK_DETAIL(recordingId ?? ""),
      });
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
    },
  });

  const generateMut = useMutation({
    mutationFn: () => apiClient.recordings.generate(recordingId!),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({
        queryKey: QK_DETAIL(recordingId ?? ""),
      });
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
      navigate(routePath.workflowDetail(result.workflow_id));
    },
  });

  const recording = detailQuery.data;
  const events = useMemo(() => {
    if (!recording) return [];
    if (recording.status === "active" && liveQuery.data?.length) {
      return liveQuery.data as Record<string, unknown>[];
    }
    return recording.events as Record<string, unknown>[];
  }, [recording, liveQuery.data]);

  if (!recordingId) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("recordings.noId")}
      </div>
    );
  }

  if (detailQuery.isLoading) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("common.loading")}
      </div>
    );
  }

  if (detailQuery.error || !recording) {
    return (
      <div className="p-6 text-sm text-destructive">
        {(detailQuery.error as Error | undefined)?.message ??
          t("recordings.notFound")}
      </div>
    );
  }

  const generateError =
    generateMut.error instanceof ApiError
      ? `${generateMut.error.status}: ${JSON.stringify(generateMut.error.body)}`
      : generateMut.error instanceof Error
        ? generateMut.error.message
        : null;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="flex items-center justify-between border-b bg-card/40 px-6 py-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(routePath.recordings())}
          >
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
            {t("common.back")}
          </Button>
          <div>
            <h1 className="text-lg font-semibold">
              {recording.name || recording.id.slice(0, 8)}
            </h1>
            <p className="text-sm text-muted-foreground">
              {recording.start_url || t("recordings.noStartUrl")}
            </p>
          </div>
          <Badge>{t(`recordings.status.${recording.status}`)}</Badge>
        </div>
        <div className="flex gap-2">
          {recording.status === "active" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => stopMut.mutate()}
              disabled={stopMut.isPending}
            >
              <Square className="mr-1.5 h-3.5 w-3.5" />
              {stopMut.isPending ? t("recordings.stopping") : t("recordings.stop")}
            </Button>
          )}
          {(recording.status === "stopped" ||
            recording.status === "synthesized") && (
            <Button
              size="sm"
              onClick={() => generateMut.mutate()}
              disabled={generateMut.isPending}
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              {generateMut.isPending
                ? t("recordings.generating")
                : recording.generated_workflow_id
                  ? t("recordings.openWorkflow")
                  : t("recordings.generateWorkflow")}
            </Button>
          )}
          {recording.generated_workflow_id && (
            <Button variant="outline" size="sm" asChild>
              <Link to={routePath.workflowDetail(recording.generated_workflow_id)}>
                {t("recordings.viewWorkflow")}
              </Link>
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 border-b px-6 py-4 text-sm md:grid-cols-4">
        <div>
          <div className="text-xs text-muted-foreground">
            {t("recordings.meta.started")}
          </div>
          <div>{formatTime(recording.started_at)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">
            {t("recordings.meta.stopped")}
          </div>
          <div>{formatTime(recording.stopped_at)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">
            {t("recordings.meta.events")}
          </div>
          <div>{events.length}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">
            {t("recordings.meta.profile")}
          </div>
          <div>
            {recording.browser_profile_id
              ? recording.browser_profile_id.slice(0, 8)
              : t("recordings.profileNone")}
          </div>
        </div>
      </div>

      {generateError && (
        <div className="mx-6 mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {generateError}
        </div>
      )}

      <div className="flex-1 p-6">
        <h2 className="mb-3 text-sm font-medium">{t("recordings.eventsTitle")}</h2>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {recording.status === "active"
              ? t("recordings.eventsWaiting")
              : t("recordings.eventsEmpty")}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">#</TableHead>
                <TableHead>{t("recordings.eventsTable.time")}</TableHead>
                <TableHead>{t("recordings.eventsTable.summary")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((event, idx) => (
                <TableRow key={idx}>
                  <TableCell className="text-xs text-muted-foreground">
                    {idx + 1}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {formatTime(
                      typeof event.ts === "string" ? event.ts : null,
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {eventSummary(event)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
