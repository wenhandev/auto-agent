import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

function envBadge(status: WorkerOut["environment_status"]) {
  const map = {
    ready: { label: "就绪", variant: "default" as const },
    degraded: { label: "降级", variant: "secondary" as const },
    not_ready: { label: "未就绪", variant: "destructive" as const },
    unknown: { label: "未知", variant: "outline" as const },
  };
  return map[status] ?? map.unknown;
}

function approvalBadge(status: WorkerApprovalStatus) {
  const map = {
    pending: { label: "待授权", variant: "secondary" as const },
    approved: { label: "已授权", variant: "default" as const },
    rejected: { label: "已拒绝", variant: "destructive" as const },
  };
  return map[status] ?? map.pending;
}

function canManageWorkers(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin";
}

export function WorkersPanel() {
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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Workers</CardTitle>
        <CardDescription>
          已通过 Auto Agent Client 登录的本机设备（约 10 秒刷新）。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {workersQuery.isLoading && (
          <p className="text-sm text-muted-foreground">加载中…</p>
        )}
        {workersQuery.error && (
          <p className="text-sm text-destructive">无法加载 Workers 列表</p>
        )}
        {workersQuery.data && workersQuery.data.length === 0 && (
          <p className="text-sm text-muted-foreground">
            暂无已连接的设备。请让用户安装{" "}
            <strong>Auto Agent Client</strong>，使用云地址登录；管理员在此批准设备。{" "}
            <Link
              to={ROUTES.clientDownload}
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              下载客户端
            </Link>
          </p>
        )}
        {workersQuery.data && workersQuery.data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称 / 主机</TableHead>
                <TableHead>用户</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>授权</TableHead>
                <TableHead>环境</TableHead>
                <TableHead>标签</TableHead>
                <TableHead>运行中</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {workersQuery.data.map((worker) => {
                const env = envBadge(worker.environment_status);
                const approval = approvalBadge(worker.approval_status);
                const failedChecks = worker.environment_checks.filter(
                  (c) => c.status === "fail" || c.status === "warn",
                );
                return (
                  <TableRow key={worker.id}>
                    <TableCell>
                      <div className="font-medium">
                        {worker.display_name || worker.hostname}
                      </div>
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
                        {worker.status === "online" ? "在线" : "离线"}
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
                              批准
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={actionPending}
                              onClick={() => {
                                if (
                                  window.confirm(
                                    `拒绝 Worker「${worker.display_name || worker.hostname}」？`,
                                  )
                                ) {
                                  rejectMutation.mutate(worker.id);
                                }
                              }}
                            >
                              <X className="mr-1 h-4 w-4" />
                              拒绝
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
                                  `撤销 Worker「${worker.display_name || worker.hostname}」？`,
                                )
                              ) {
                                revokeMutation.mutate(worker.id);
                              }
                            }}
                          >
                            <Trash2 className="mr-1 h-4 w-4" />
                            撤销
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
