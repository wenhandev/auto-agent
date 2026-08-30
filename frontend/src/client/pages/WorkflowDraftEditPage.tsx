import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ReactFlowProvider } from "@xyflow/react";
import { ArrowLeft, Upload } from "lucide-react";
import { WorkflowCanvas } from "@/components/WorkflowCanvas";
import { ChatPanelSlot } from "@/pages/ChatPanelSlot";
import { WorkflowCredentialsPanel } from "@/pages/WorkflowCredentialsPanel";
import { WorkflowTriggersPanel } from "@/pages/WorkflowTriggersPanel";
import { RunLog } from "@/components/RunLog";
import { useStore } from "@/store";
import { usePlatformStore } from "@/platformStore";
import type { Workflow } from "@/types";
import type { WorkflowVersionOut } from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  DesktopApiError,
  fetchDraft,
  publishDraft,
  saveDraft,
} from "../api";

interface DraftRecord {
  local_id: string;
  name?: string;
  workflow_id?: string | null;
  draft_json?: Workflow;
}

export function WorkflowDraftEditPage() {
  const { t } = useTranslation();
  const { draftId } = useParams<{ draftId: string }>();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DraftRecord | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);

  const editorId = draft?.workflow_id ?? draft?.local_id ?? "";
  const platformWorkflowId = usePlatformStore((s) => s.currentWorkflowId);
  const isWorkflowDirty = usePlatformStore((s) => s.isWorkflowDirty);

  const loadDraft = useCallback(async () => {
    if (!draftId) return;
    setLoading(true);
    setError(null);
    try {
      const row = (await fetchDraft(draftId)) as DraftRecord;
      const workflow = row.draft_json;
      if (!workflow) throw new Error("draft payload missing");
      setDraft(row);
      setTitle(row.name ?? draftId);
      const wfId = row.workflow_id ?? row.local_id;
      useStore.getState().setWorkflow(workflow);
      usePlatformStore.getState().setCurrentWorkflow(wfId, workflow, null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  useEffect(() => {
    void loadDraft();
    return () => {
      usePlatformStore.getState().clearCurrentWorkflow();
    };
  }, [loadDraft]);

  async function onSave() {
    if (!draftId || !draft) return;
    const workflow = usePlatformStore.getState().currentWorkflow;
    if (!workflow) return;
    setSaving(true);
    setError(null);
    try {
      const saved = (await saveDraft({
        local_id: draftId,
        draft_json: workflow,
        workflow_id: draft.workflow_id ?? undefined,
        name: title.trim() || draft.name,
      })) as DraftRecord;
      setDraft(saved);
      usePlatformStore.getState().clearWorkflowDirty();
    } catch (err) {
      setError(
        err instanceof DesktopApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setSaving(false);
    }
  }

  async function onPublish() {
    if (!draftId) return;
    if (isWorkflowDirty) {
      await onSave();
    }
    setPublishing(true);
    setError(null);
    try {
      await publishDraft(draftId);
      if (draft?.workflow_id) {
        navigate(`/workflows/${draft.workflow_id}`);
      } else {
        navigate("/workflows");
      }
    } catch (err) {
      setError(
        err instanceof DesktopApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setPublishing(false);
    }
  }

  const onChatWorkflowUpdated = useCallback(
    (nextVersion: WorkflowVersionOut) => {
      if (!draft?.workflow_id) return;
      usePlatformStore.getState().clearWorkflowDirty();
      useStore.getState().setWorkflow(nextVersion.workflow);
      usePlatformStore.getState().setCurrentWorkflow(
        draft.workflow_id,
        nextVersion.workflow,
        nextVersion,
      );
      void saveDraft({
        local_id: draft.local_id,
        draft_json: nextVersion.workflow,
        workflow_id: draft.workflow_id,
        name: title.trim() || draft.name,
        cloud_version_id: nextVersion.id,
      }).catch(() => {
        // chat saved to cloud; local sync is best-effort
      });
    },
    [draft, title],
  );

  if (!draftId) {
    return null;
  }

  if (loading) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("pages.workflowDetail.loading")}
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="p-6 text-sm text-destructive">
        {error ?? t("desktop.workflows.draftNotFound")}
      </div>
    );
  }

  const linkedCloudId = draft.workflow_id;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b bg-card/40 px-4 py-2">
        <Button variant="ghost" size="icon" asChild className="shrink-0">
          <Link to="/workflows" aria-label={t("desktop.workflows.back")}>
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <input
          className={cn(
            "min-w-[220px] rounded-md border border-transparent bg-transparent px-2 py-1.5 text-base font-semibold outline-none transition-colors",
            "hover:border-input hover:bg-accent/40",
            "focus:border-ring focus:bg-background focus:ring-2 focus:ring-ring/30",
          )}
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            usePlatformStore.getState().markWorkflowDirty();
          }}
          aria-label={t("pages.workflowDetail.nameAria")}
        />
        <Badge variant="outline">{t("desktop.workflows.localDraft")}</Badge>
        {isWorkflowDirty && (
          <Badge variant="outline" className="border-amber-500/50 text-amber-600">
            {t("pages.workflowDetail.unsaved")}
          </Badge>
        )}
        <div className="flex-1" />
        <Button
          variant="secondary"
          disabled={!isWorkflowDirty || saving}
          onClick={() => void onSave()}
        >
          {saving ? t("common.saving") : t("common.save")}
        </Button>
        {linkedCloudId ? (
          <Button
            disabled={publishing}
            onClick={() => void onPublish()}
          >
            <Upload className="mr-2 h-4 w-4" />
            {publishing
              ? t("desktop.workflows.publishing")
              : t("desktop.workflows.publish")}
          </Button>
        ) : null}
      </div>

      {error && (
        <p className="border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 border-r">
          {platformWorkflowId === editorId ? (
            <ReactFlowProvider key={draft.local_id}>
              <WorkflowCanvas />
            </ReactFlowProvider>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {t("pages.workflowDetail.syncing")}
            </div>
          )}
        </div>
        <div className="flex w-[380px] shrink-0 min-h-0 flex-col bg-card/30">
          {linkedCloudId ? (
            <>
              <div className="flex min-h-0 flex-1 flex-col overflow-auto">
                <ChatPanelSlot
                  workflowId={linkedCloudId}
                  onWorkflowUpdated={onChatWorkflowUpdated}
                />
              </div>
              <Separator />
              <div className="max-h-[220px] overflow-auto">
                <WorkflowTriggersPanel workflowId={linkedCloudId} />
              </div>
              <Separator />
              <div className="max-h-[280px] overflow-auto">
                <WorkflowCredentialsPanel workflowId={linkedCloudId} />
              </div>
              <Separator />
            </>
          ) : (
            <div className="p-4 text-sm text-muted-foreground">
              {t("desktop.workflows.draftOfflineHint")}
            </div>
          )}
          <div className="flex min-h-0 flex-1 flex-col">
            <RunLog />
          </div>
        </div>
      </div>
    </div>
  );
}
