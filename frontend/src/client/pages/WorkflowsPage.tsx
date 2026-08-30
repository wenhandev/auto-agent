import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, RefreshCw, Upload } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  fetchCloudWorkflows,
  isSessionAuthError,
  listDrafts,
  pullCloudWorkflow,
  publishDraft,
} from "../api";
import { useDesktopAuth } from "../DesktopAuthContext";
import type { CloudWorkflowListItem, WorkflowDraftMeta } from "../types";

export function WorkflowsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { logout } = useDesktopAuth();
  const [cloud, setCloud] = useState<CloudWorkflowListItem[]>([]);
  const [drafts, setDrafts] = useState<WorkflowDraftMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [pulling, setPulling] = useState<string | null>(null);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    setSessionExpired(false);
    const draftPromise = listDrafts().catch((err) => {
      const msg = err instanceof Error ? err.message : String(err);
      setError(t("desktop.workflows.localDraftsError", { error: msg }));
      return [] as WorkflowDraftMeta[];
    });
    try {
      const wf = await fetchCloudWorkflows();
      const local = await draftPromise;
      setCloud(wf);
      setDrafts(local);
    } catch (err) {
      if (isSessionAuthError(err)) {
        setSessionExpired(true);
        setError(t("desktop.workflows.sessionExpired"));
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        setError((prev) =>
          prev
            ? `${prev}; ${t("desktop.workflows.cloudError", { error: msg })}`
            : t("desktop.workflows.cloudError", { error: msg }),
        );
      }
      const local = await draftPromise;
      setDrafts(local);
    }
  }

  useEffect(() => {
    void refresh();
  }, [t]);

  async function onPublish(localId: string) {
    setPublishing(localId);
    setError(null);
    try {
      await publishDraft(localId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPublishing(null);
    }
  }

  async function onPull(workflowId: string) {
    setPulling(workflowId);
    try {
      const draft = await pullCloudWorkflow(workflowId);
      await refresh();
      navigate(`/drafts/${draft.local_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPulling(null);
    }
  }

  async function onCreateWorkflow(e: React.FormEvent) {
    e.preventDefault();
    if (!createName.trim()) {
      setCreateError(t("pages.workflows.nameRequired"));
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const wf = await apiClient.workflows.create({
        name: createName.trim(),
        description: createDescription.trim() || null,
      });
      setCreateOpen(false);
      setCreateName("");
      setCreateDescription("");
      navigate(`/workflows/${wf.id}`);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
          : err instanceof Error
            ? err.message
            : String(err);
      setCreateError(message);
    } finally {
      setCreating(false);
    }
  }

  const draftByWorkflow = new Map(
    drafts
      .filter((d) => d.workflow_id)
      .map((d) => [d.workflow_id as string, d]),
  );

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("desktop.workflows.title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("desktop.workflows.subtitle")}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            {t("pages.workflows.newButton")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t("desktop.workflows.refresh")}
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <p>{error}</p>
          {sessionExpired && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() => logout()}
            >
              {t("desktop.workflows.signInAgain")}
            </Button>
          )}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t("desktop.workflows.cloudTitle")}
          </CardTitle>
          <CardDescription>
            {t("desktop.workflows.cloudDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {cloud.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("desktop.workflows.empty")}
            </p>
          ) : (
            cloud.map((wf) => {
              const draft = draftByWorkflow.get(wf.id);
              return (
                <div
                  key={wf.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="font-medium">{wf.name}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {wf.id}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {draft ? (
                      <Badge variant="secondary">
                        {t("desktop.workflows.localDraft")}
                      </Badge>
                    ) : null}
                    <Button size="sm" asChild>
                      <Link to={`/workflows/${wf.id}`}>
                        {t("desktop.workflows.edit")}
                      </Link>
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={pulling === wf.id}
                      onClick={() => void onPull(wf.id)}
                    >
                      {t("desktop.workflows.pullDraft")}
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t("desktop.workflows.localTitle")}
          </CardTitle>
          <CardDescription>
            {t("desktop.workflows.localDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {drafts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("desktop.workflows.localEmpty")}
            </p>
          ) : (
            drafts.map((draft) => (
              <div
                key={draft.local_id}
                className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <div className="font-medium">{draft.name}</div>
                    {draft.publish_queued ? (
                      <Badge variant="outline">
                        {t("desktop.workflows.queuedPublish")}
                      </Badge>
                    ) : null}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {draft.local_id}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {draft.workflow_id ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={publishing === draft.local_id}
                      onClick={() => void onPublish(draft.local_id)}
                    >
                      <Upload className="mr-1.5 h-3.5 w-3.5" />
                      {t("desktop.workflows.publish")}
                    </Button>
                  ) : null}
                  <Button variant="outline" size="sm" asChild>
                    <Link to={`/drafts/${draft.local_id}`}>
                      {t("desktop.workflows.edit")}
                    </Link>
                  </Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) {
            setCreateName("");
            setCreateDescription("");
            setCreateError(null);
          }
        }}
      >
        <DialogContent>
          <form onSubmit={(e) => void onCreateWorkflow(e)} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>{t("pages.workflows.createModalTitle")}</DialogTitle>
            </DialogHeader>
            <div className="grid gap-2">
              <Label htmlFor="desktop-wf-name">
                {t("pages.workflows.nameLabel")}
              </Label>
              <Input
                id="desktop-wf-name"
                autoFocus
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder={t("pages.workflows.namePlaceholder")}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="desktop-wf-desc">
                {t("pages.workflows.descriptionLabel")}
              </Label>
              <Textarea
                id="desktop-wf-desc"
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
                rows={3}
                placeholder={t("pages.workflows.descriptionPlaceholder")}
              />
            </div>
            {createError && (
              <div className="text-sm text-destructive">{createError}</div>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateOpen(false)}
              >
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={creating}>
                {creating ? t("common.creating") : t("common.create")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
