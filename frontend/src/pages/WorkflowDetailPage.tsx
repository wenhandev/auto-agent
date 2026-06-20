import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ReactFlowProvider } from "@xyflow/react";
import { ApprovalBanner } from "@/components/ApprovalBanner";
import { RunLog } from "@/components/RunLog";
import { RunNowDialog } from "@/components/RunNowDialog";
import { WorkflowCanvas } from "@/components/WorkflowCanvas";
import { apiClient, ApiError } from "@/api-platform";
import { useStore } from "@/store";
import { usePlatformStore } from "@/platformStore";
import type { PlatformRunStatus } from "@/platformStore";
import { routePath } from "@/routes";
import type {
  RunCreate,
  RunStatus,
  WorkflowOut,
  WorkflowVersionOut,
} from "@/types-platform";
import { ChatPanelSlot } from "./ChatPanelSlot";
import { WorkflowCredentialsPanel } from "./WorkflowCredentialsPanel";
import { WorkflowDetailHeader } from "./WorkflowDetailHeader";
import { WorkflowTriggersPanel } from "./WorkflowTriggersPanel";
import { Separator } from "@/components/ui/separator";

function workflowQueryKey(id: string) {
  return ["workflows", "detail", id] as const;
}

function versionsQueryKey(id: string) {
  return ["workflows", "versions", id] as const;
}

function applyToBothStores(
  workflow: WorkflowOut,
  version: WorkflowVersionOut | null,
) {
  if (version) {
    useStore.getState().setWorkflow(version.workflow);
    usePlatformStore.getState().setCurrentWorkflow(
      workflow.id,
      version.workflow,
      version,
    );
  }
}

function mapRunStatus(s: RunStatus): PlatformRunStatus {
  return s;
}

export function WorkflowDetailPage() {
  const { t } = useTranslation();
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  const platformWorkflowId = usePlatformStore((s) => s.currentWorkflowId);
  const runStatus = usePlatformStore((s) => s.currentRunStatus);
  const currentRunId = usePlatformStore((s) => s.currentRunId);
  const pendingApproval = usePlatformStore((s) => s.pendingApproval);
  const currentVersion = usePlatformStore((s) => s.currentVersion);
  const currentWorkflow = usePlatformStore((s) => s.currentWorkflow);
  const versionsCached = usePlatformStore((s) => s.versions);
  const isWorkflowDirty = usePlatformStore((s) => s.isWorkflowDirty);
  const [runDialogOpen, setRunDialogOpen] = useState(false);

  const detailQuery = useQuery({
    queryKey: workflowQueryKey(workflowId ?? ""),
    queryFn: () => apiClient.workflows.get(workflowId!),
    enabled: !!workflowId,
  });

  const versionsQuery = useQuery({
    queryKey: versionsQueryKey(workflowId ?? ""),
    queryFn: () => apiClient.workflows.listVersions(workflowId!),
    enabled: !!workflowId,
  });

  useEffect(() => {
    if (detailQuery.data) {
      applyToBothStores(detailQuery.data, detailQuery.data.current_version);
    }
  }, [detailQuery.data]);

  useEffect(() => {
    if (versionsQuery.data) {
      usePlatformStore.getState().setVersions(versionsQuery.data);
    }
  }, [versionsQuery.data]);

  useEffect(() => {
    return () => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        try {
          ws.close();
        } catch {
          // ignore
        }
      }
      wsRef.current = null;
      usePlatformStore.getState().setActiveWS(null);
    };
  }, []);

  const renameMut = useMutation({
    mutationFn: (newName: string) =>
      apiClient.workflows.update(workflowId!, { name: newName }),
    onSuccess: (wf) => {
      queryClient.setQueryData(workflowQueryKey(workflowId!), wf);
      void queryClient.invalidateQueries({ queryKey: ["workflows", "list"] });
    },
  });

  const saveMut = useMutation({
    mutationFn: () => {
      const wf = usePlatformStore.getState().currentWorkflow;
      if (!wf) throw new Error("no workflow to save");
      return apiClient.workflows.createVersion(workflowId!, {
        workflow: wf,
        authored_by: "manual",
      });
    },
    onSuccess: (nextVersion) => {
      if (!detail) return;
      usePlatformStore.getState().clearWorkflowDirty();
      queryClient.setQueryData<WorkflowOut>(
        workflowQueryKey(detail.id),
        (prev) =>
          prev ? { ...prev, current_version: nextVersion } : prev,
      );
      applyToBothStores(detail, nextVersion);
      void queryClient.invalidateQueries({
        queryKey: versionsQueryKey(detail.id),
      });
    },
    onError: (err: unknown) => {
      console.error("workflow save failed", err);
    },
  });

  const runMut = useMutation({
    mutationFn: (body?: RunCreate) => apiClient.runs.create(workflowId!, body),
    onSuccess: (run) => {
      setRunDialogOpen(false);
      usePlatformStore
        .getState()
        .setCurrentRun(run.id, mapRunStatus(run.status));
      if (run.pending_approval) {
        usePlatformStore.getState().setPendingApproval(run.pending_approval);
      }
      useStore.getState().resetRun();
      navigate(routePath.runReplay(run.id));
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? `run create failed: ${err.status}`
          : err instanceof Error
            ? err.message
            : String(err);
      console.error(message, err);
    },
  });

  const abortMut = useMutation({
    mutationFn: (runId: string) => apiClient.runs.abort(runId),
    onError: (err: unknown) => {
      console.error("run abort failed", err);
    },
  });

  const onRun = useCallback(() => {
    if (!workflowId) return;
    setRunDialogOpen(true);
  }, [workflowId]);

  const onStartRun = useCallback(
    (body: RunCreate) => {
      runMut.mutate(body);
    },
    [runMut],
  );

  const onAbort = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN && currentRunId) {
      try {
        ws.send(JSON.stringify({ type: "abort", run_id: currentRunId }));
      } catch (err) {
        console.error("ws abort send failed", err);
      }
    }
    if (currentRunId) {
      abortMut.mutate(currentRunId);
    }
  }, [currentRunId, abortMut]);

  const onSelectVersion = useCallback(
    async (versionId: string) => {
      const version = versionsCached.find((v) => v.id === versionId);
      if (!version) return;
      useStore.getState().setWorkflow(version.workflow);
      usePlatformStore.getState().setCurrentWorkflow(
        workflowId!,
        version.workflow,
        version,
      );
      usePlatformStore.getState().clearWorkflowDirty();
    },
    [versionsCached, workflowId],
  );

  const onSave = useCallback(() => {
    saveMut.mutate();
  }, [saveMut]);

  const isQueuedOrRunning =
    runStatus === "queued" || runStatus === "running";
  const runDisabled = isQueuedOrRunning || !detailQuery.data;
  const abortDisabled = !isQueuedOrRunning || !currentRunId;

  const detail = detailQuery.data;
  const versions = versionsQuery.data ?? versionsCached;
  const versionForHeader = currentVersion ?? detail?.current_version ?? null;

  const onChatWorkflowUpdated = useCallback(
    (nextVersion: WorkflowVersionOut) => {
      if (!detail) return;
      usePlatformStore.getState().clearWorkflowDirty();
      queryClient.setQueryData<WorkflowOut>(
        workflowQueryKey(detail.id),
        (prev) =>
          prev ? { ...prev, current_version: nextVersion } : prev,
      );
      applyToBothStores(detail, nextVersion);
      void queryClient.invalidateQueries({
        queryKey: versionsQueryKey(detail.id),
      });
    },
    [detail, queryClient],
  );

  if (!workflowId) {
    navigate(routePath.workflows(), { replace: true });
    return null;
  }

  if (detailQuery.isLoading) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("pages.workflowDetail.loading")}
      </div>
    );
  }

  if (detailQuery.error) {
    const err = detailQuery.error;
    return (
      <div className="p-6 text-sm text-destructive">
        {(err as Error).message}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("pages.workflowDetail.notFound")}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkflowDetailHeader
        name={detail.name}
        onRename={(name) => renameMut.mutate(name)}
        renameDisabled={renameMut.isPending}
        versions={versions}
        currentVersionId={versionForHeader?.id ?? null}
        onSelectVersion={onSelectVersion}
        runStatus={runStatus}
        onRun={onRun}
        onAbort={onAbort}
        runDisabled={runDisabled}
        abortDisabled={abortDisabled}
        isDirty={isWorkflowDirty}
        onSave={onSave}
        saveDisabled={!isWorkflowDirty || saveMut.isPending}
        isSaving={saveMut.isPending}
      />
      {currentRunId && isQueuedOrRunning && (
        <ApprovalBanner
          runId={currentRunId}
          pending={pendingApproval}
          onResolved={() => usePlatformStore.getState().setPendingApproval(null)}
        />
      )}
      <RunNowDialog
        open={runDialogOpen}
        onOpenChange={setRunDialogOpen}
        workflowId={workflowId}
        parameters={currentWorkflow?.parameters ?? []}
        onSubmit={onStartRun}
        submitting={runMut.isPending}
      />
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 border-r">
          {platformWorkflowId === workflowId ? (
            <ReactFlowProvider key={versionForHeader?.id ?? workflowId}>
              <WorkflowCanvas />
            </ReactFlowProvider>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {t("pages.workflowDetail.syncing")}
            </div>
          )}
        </div>
        <div className="flex w-[380px] shrink-0 min-h-0 flex-col bg-card/30">
          <div className="flex min-h-0 flex-1 flex-col overflow-auto">
            <ChatPanelSlot
              workflowId={workflowId}
              onWorkflowUpdated={onChatWorkflowUpdated}
            />
          </div>
          <Separator />
          <div className="max-h-[220px] overflow-auto">
            <WorkflowTriggersPanel workflowId={workflowId} />
          </div>
          <Separator />
          <div className="max-h-[280px] overflow-auto">
            <WorkflowCredentialsPanel workflowId={workflowId} />
          </div>
          <Separator />
          <div className="flex min-h-0 flex-1 flex-col">
            <RunLog />
          </div>
        </div>
      </div>
    </div>
  );
}
