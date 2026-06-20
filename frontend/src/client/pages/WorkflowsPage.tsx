import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, RefreshCw, Upload } from "lucide-react";
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
  fetchCloudWorkflows,
  listDrafts,
  pullCloudWorkflow,
  publishDraft,
} from "../api";
import type { CloudWorkflowListItem, WorkflowDraftMeta } from "../types";

export function WorkflowsPage() {
  const [cloud, setCloud] = useState<CloudWorkflowListItem[]>([]);
  const [drafts, setDrafts] = useState<WorkflowDraftMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pulling, setPulling] = useState<string | null>(null);
  const [publishing, setPublishing] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const [wf, local] = await Promise.all([fetchCloudWorkflows(), listDrafts()]);
      setCloud(wf);
      setDrafts(local);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

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
      await pullCloudWorkflow(workflowId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPulling(null);
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
          <h1 className="text-2xl font-semibold tracking-tight">Workflows</h1>
          <p className="text-sm text-muted-foreground">
            Cloud-published workflows and local drafts.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cloud workflows</CardTitle>
          <CardDescription>Read-only view; pull to create a local draft</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {cloud.length === 0 ? (
            <p className="text-sm text-muted-foreground">No workflows found.</p>
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
                    <div className="truncate text-xs text-muted-foreground">{wf.id}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {draft ? (
                      <Badge variant="secondary">Local draft</Badge>
                    ) : (
                      <Badge variant="outline">Cloud only</Badge>
                    )}
                    <Button variant="outline" size="sm" asChild>
                      <Link to={`/workflows/${wf.id}`}>View</Link>
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={pulling === wf.id}
                      onClick={() => void onPull(wf.id)}
                    >
                      Pull draft
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
          <CardTitle className="text-base">Local drafts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {drafts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No local drafts yet.</p>
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
                      <Badge variant="outline">Queued for publish</Badge>
                    ) : null}
                  </div>
                  <div className="text-xs text-muted-foreground">{draft.local_id}</div>
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
                      Publish
                    </Button>
                  ) : null}
                  <Button variant="outline" size="sm" asChild>
                    <Link to={`/drafts/${draft.local_id}`}>Open</Link>
                  </Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Full editing is available in the web app.{" "}
        <a
          href="/"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 underline"
        >
          Open in web <ExternalLink className="h-3 w-3" />
        </a>
      </p>
    </div>
  );
}
