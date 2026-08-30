import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Trash2, X } from "lucide-react";
import { apiClient } from "@/api-platform";
import { useAuth } from "@/auth/useAuth";
import { ROUTES } from "@/routes";
import type { WorkerApprovalStatus, WorkerOut } from "@/types-platform";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const QK_WORKERS = ["workers", "list"] as const;

function canManageWorkers(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin";
}

export function WorkersPanel() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { user, bypass } = useAuth();
  const canManage = bypass || canManageWorkers(user?.role);

  const workersQuery = useQuery({
    queryKey: QK_WORKERS,
    queryFn: () => apiClient.workers.list(),
    refetchInterval: 10_000,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: QK_WORKERS });

  const approveMutation = useMutation({
    mutationFn: (workerId: string) => apiClient.workers.approve(workerId),
    onSuccess: invalidate,
  });

  const rejectMutation = useMutation({
    mutationFn: (workerId: string) => apiClient.workers.reject(workerId),
    onSuccess: invalidate,
  });

  const revokeMutation = useMutation({
    mutationFn: (workerId: string) => apiClient.workers.revoke(workerId),
    onSuccess: invalidate,
  });

  const actionPending =
    approveMutation.isPending ||
    rejectMutation.isPending ||
    revokeMutation.isPending;

  function envBadge(status: WorkerOut["environment_status"]) {
    const map = {
      ready: { label: t("pages.settings.workersEnvReady"), variant: "default" as const },
      degraded: {
        label: t("pages.settings.workersEnvDegraded"),
        variant: "secondary" as const,
      },
      not_ready: {
        label: t("pages.settings.workersEnvNotReady"),
        variant: "destructive" as const,
      },
      unknown: {
        label: t("pages.settings.workersEnvUnknown"),
        variant: "outline" as const,
      },
    };
    return map[status] ?? map.unknown;
  }

  function approvalBadge(status: WorkerApprovalStatus) {
    const map = {
      pending: {
        label: t("pages.settings.workersApprovalPending"),
        variant: "secondary" as const,
      },
      approved: {
        label: t("pages.settings.workersApprovalApproved"),
        variant: "default" as const,
      },
      rejected: {
        label: t("pages.settings.workersApprovalRejected"),
        variant: "destructive" as const,
      },
    };
    return map[status] ?? map.pending;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("pages.settings.workersTitle")}</CardTitle>
        <CardDescription>{t("pages.settings.workersDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        {workersQuery.isLoading && (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        )}
        {workersQuery.error && (
          <p className="text-sm text-destructive">
            {t("pages.settings.workersLoadError")}
          </p>
        )}
        {workersQuery.data && workersQuery.data.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {t("pages.settings.workersEmpty")}{" "}
            <Link
              to={ROUTES.clientDownload}
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              {t("pages.settings.workersDownloadClient")}
            </Link>
          </p>
        )}
        {workersQuery.data && workersQuery.data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("pages.settings.workersTableNameHost")}</TableHead>
                <TableHead>{t("pages.settings.workersTableUser")}</TableHead>
                <TableHead>{t("pages.settings.workersTableStatus")}</TableHead>
                <TableHead>{t("pages.settings.workersTableApproval")}</TableHead>
                <TableHead>{t("pages.settings.workersTableEnvironment")}</TableHead>
                <TableHead>{t("pages.settings.workersTableTags")}</TableHead>
                <TableHead>{t("pages.settings.workersTableRunning")}</TableHead>
                <TableHead className="text-right">
                  {t("pages.settings.workersTableActions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {workersQuery.data.map((worker) => {
                const env = envBadge(worker.environment_status);
                const approval = approvalBadge(worker.approval_status);
                const failedChecks = worker.environment_checks.filter(
                  (c) => c.status === "fail" || c.status === "warn",
                );
                const workerName = worker.display_name || worker.hostname;
                return (
                  <TableRow key={worker.id}>
                    <TableCell>
                      <div className="font-medium">{workerName}</div>
                      <div className="text-xs text-muted-foreground">
                        {worker.hostname}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {worker.user_email ?? worker.user_id.slice(0, 8)}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          worker.status === "online" ? "default" : "secondary"
                        }
                      >
                        {worker.status === "online"
                          ? t("pages.settings.workersOnline")
                          : t("pages.settings.workersOffline")}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={approval.variant}>{approval.label}</Badge>
                    </TableCell>
                    <TableCell>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Badge variant={env.variant}>{env.label}</Badge>
                          </TooltipTrigger>
                          {failedChecks.length > 0 && (
                            <TooltipContent className="max-w-xs">
                              <ul className="list-disc pl-4 text-xs">
                                {failedChecks.map((c) => (
                                  <li key={c.id}>
                                    {c.id}: {c.message ?? c.status}
                                  </li>
                                ))}
                              </ul>
                            </TooltipContent>
                          )}
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                    <TableCell className="text-xs">
                      {worker.tags.join(", ")}
                    </TableCell>
                    <TableCell>
                      {worker.active_runs} / {worker.max_concurrent_runs}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        {canManage && worker.approval_status === "pending" && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={actionPending}
                              onClick={() =>
                                approveMutation.mutate(worker.id)
                              }
                            >
                              <Check className="mr-1 h-4 w-4" />
                              {t("pages.settings.workersApprove")}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={actionPending}
                              onClick={() => {
                                if (
                                  window.confirm(
                                    t("pages.settings.workersRejectConfirm", {
                                      name: workerName,
                                    }),
                                  )
                                ) {
                                  rejectMutation.mutate(worker.id);
                                }
                              }}
                            >
                              <X className="mr-1 h-4 w-4" />
                              {t("pages.settings.workersReject")}
                            </Button>
                          </>
                        )}
                        {canManage && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={actionPending}
                            onClick={() => {
                              if (
                                window.confirm(
                                  t("pages.settings.workersRevokeConfirm", {
                                    name: workerName,
                                  }),
                                )
                              ) {
                                revokeMutation.mutate(worker.id);
                              }
                            }}
                          >
                            <Trash2 className="mr-1 h-4 w-4" />
                            {t("pages.settings.workersRevoke")}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
