import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ReactFlowProvider } from "@xyflow/react";
import { ArrowLeft } from "lucide-react";
import { WorkflowCanvas } from "@/components/WorkflowCanvas";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useStore } from "@/store";
import type { Workflow } from "@/types";
import { fetchCloudWorkflow, fetchDraft } from "../api";

export function WorkflowViewPage() {
  const { workflowId, draftId } = useParams();
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const resetWorkflow = useStore((s) => s.resetWorkflowForReplay);

  const viewKey = draftId ?? workflowId ?? "";

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setError(null);
      try {
        let workflow: Workflow | undefined;
        if (draftId) {
          const draft = (await fetchDraft(draftId)) as {
            name?: string;
            draft_json?: Workflow;
          };
          workflow = draft.draft_json;
          if (!cancelled) setTitle(draft.name ?? draftId);
        } else if (workflowId) {
          const data = (await fetchCloudWorkflow(workflowId)) as {
            name?: string;
            current_version?: { workflow?: Workflow };
          };
          workflow = data.current_version?.workflow;
          if (!cancelled) setTitle(data.name ?? workflowId);
        }
        if (!workflow) throw new Error("workflow payload missing");
        if (!cancelled) resetWorkflow(workflow);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [draftId, workflowId, resetWorkflow, viewKey]);

  const canvas = useMemo(
    () => (
      <ReactFlowProvider>
        <div className="h-[520px] w-full">
          <WorkflowCanvas readOnly />
        </div>
      </ReactFlowProvider>
    ),
    [viewKey],
  );

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-auto p-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/workflows">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Workflows
          </Link>
        </Button>
        <h1 className="text-xl font-semibold">{title || "Workflow"}</h1>
      </div>

      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Read-only canvas</CardTitle>
            <CardDescription>
              v1 client view — edit in the web app or publish from a linked draft.
            </CardDescription>
          </CardHeader>
          <CardContent>{canvas}</CardContent>
        </Card>
      )}
    </div>
  );
}
