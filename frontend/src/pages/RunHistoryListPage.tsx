import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiClient } from "@/api-platform";
import { routePath } from "@/routes";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { statusBadgeVariant } from "@/lib/status";

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return "\u2014";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = seconds / 60;
  return `${minutes.toFixed(1)}m`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function RunHistoryListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const workflowFilter = params.get("workflow_id") ?? undefined;

  const listQuery = useQuery({
    queryKey: ["runs", "list", workflowFilter ?? "all"],
    queryFn: () => apiClient.runs.list(workflowFilter),
  });

  const items = listQuery.data ?? [];

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex items-baseline justify-between gap-4 border-b px-6 pb-3 pt-5">
        <div>
          <div className="text-xl font-semibold">
            {t("pages.runHistory.title")}
          </div>
          <div className="text-xs text-muted-foreground">
            {workflowFilter
              ? t("pages.runHistory.subtitleFor", {
                  workflowId: workflowFilter,
                })
              : t("pages.runHistory.subtitle")}
          </div>
        </div>
      </div>
      <div className="flex-1 p-6">
        {listQuery.error && (
          <div className="mb-3 text-sm text-destructive">
            {(listQuery.error as Error).message}
          </div>
        )}
        {listQuery.isLoading && (
          <div className="text-sm text-muted-foreground">
            {t("common.loading")}
          </div>
        )}
        {!listQuery.isLoading && items.length === 0 && (
          <div className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
            <div className="text-base font-medium text-foreground">
              {t("pages.runHistory.empty")}
            </div>
          </div>
        )}
        {!listQuery.isLoading && items.length > 0 && (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("pages.runHistory.table.workflow")}</TableHead>
                  <TableHead>{t("pages.runHistory.table.version")}</TableHead>
                  <TableHead>{t("pages.runHistory.table.status")}</TableHead>
                  <TableHead>{t("pages.runHistory.table.queued")}</TableHead>
                  <TableHead>{t("pages.runHistory.table.finished")}</TableHead>
                  <TableHead>{t("pages.runHistory.table.duration")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((row) => (
                  <TableRow
                    key={row.id}
                    className="cursor-pointer"
                    onClick={() => navigate(routePath.runReplay(row.id))}
                  >
                    <TableCell className="font-medium">
                      {row.workflow_name}
                    </TableCell>
                    <TableCell>v{row.version_index}</TableCell>
                    <TableCell>
                      <Badge variant={statusBadgeVariant(row.status)}>
                        {t(`status.${row.status}`, row.status)}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatTime(row.queued_at)}</TableCell>
                    <TableCell>{formatTime(row.finished_at)}</TableCell>
                    <TableCell>{formatDuration(row.duration_ms)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
