import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Download, FileJson, Image, Film } from "lucide-react";
import { apiClient } from "@/api-platform";
import type { RunArtifactOut } from "@/types-platform";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ImagePreviewDialog } from "@/components/ImagePreviewDialog";

interface Props {
  runId: string;
  active?: boolean;
}

function kindIcon(kind: RunArtifactOut["kind"]) {
  switch (kind) {
    case "screenshot":
      return Image;
    case "llm_trace":
      return FileJson;
    case "recording":
    case "trace":
      return Film;
    default:
      return Download;
  }
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function ArtifactCard({ runId, artifact }: { runId: string; artifact: RunArtifactOut }) {
  const { t } = useTranslation();
  const Icon = kindIcon(artifact.kind);
  const url = apiClient.runs.artifactUrl(runId, artifact.id);
  const thumbUrl =
    artifact.kind === "screenshot" && !artifact.expired
      ? apiClient.runs.artifactThumbnailUrl(runId, artifact.id)
      : null;
  const [previewOpen, setPreviewOpen] = useState(false);

  return (
    <div className="flex flex-col gap-2 rounded-md border bg-card p-2">
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant="secondary" className="text-[10px]">
              {artifact.kind}
            </Badge>
            <span className="text-[10px] text-muted-foreground">
              {formatBytes(artifact.bytes)}
            </span>
          </div>
          <p className="truncate text-xs font-medium">
            {artifact.filename || artifact.id}
          </p>
          {artifact.node_id && (
            <p className="truncate font-mono text-[10px] text-muted-foreground">
              {artifact.node_id}
            </p>
          )}
          {artifact.note && (
            <p className="text-[10px] text-muted-foreground">{artifact.note}</p>
          )}
        </div>
      </div>

      {artifact.expired ? (
        <p className="text-xs text-muted-foreground">{t("artifacts.expired")}</p>
      ) : (
        <>
          {thumbUrl && (
            <button
              type="button"
              className="block w-full overflow-hidden rounded border bg-muted/30"
              title={t("imagePreview.clickToEnlarge")}
              onClick={() => setPreviewOpen(true)}
            >
              <img
                src={thumbUrl}
                alt={artifact.filename ?? artifact.kind}
                className="max-h-32 w-full cursor-zoom-in object-contain"
              />
            </button>
          )}
          <Button asChild size="sm" variant="outline" className="h-7 text-xs">
            <a href={url} target="_blank" rel="noreferrer" download>
              <Download className="mr-1 h-3 w-3" />
              {t("artifacts.download")}
            </a>
          </Button>
          {thumbUrl && (
            <ImagePreviewDialog
              open={previewOpen}
              onOpenChange={setPreviewOpen}
              src={url}
              alt={artifact.filename ?? artifact.kind}
              title={artifact.filename ?? artifact.kind}
            />
          )}
        </>
      )}
    </div>
  );
}

export function ArtifactsPanel({ runId, active = false }: Props) {
  const { t } = useTranslation();

  const query = useQuery({
    queryKey: ["runs", "artifacts", runId],
    queryFn: () => apiClient.runs.listArtifacts(runId),
    enabled: !!runId,
    refetchInterval: active ? 3000 : false,
  });

  const artifacts = query.data ?? [];
  const grouped = artifacts.reduce<Record<string, RunArtifactOut[]>>(
    (acc, item) => {
      const key = item.kind;
      acc[key] = acc[key] ?? [];
      acc[key].push(item);
      return acc;
    },
    {},
  );

  return (
    <div className="flex flex-col gap-2 border-t p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("artifacts.title")}
        </h3>
        <Badge variant="outline" className="text-[10px]">
          {artifacts.length}
        </Badge>
      </div>

      {query.isLoading && (
        <p className="text-xs text-muted-foreground">{t("common.loading")}</p>
      )}

      {query.error && (
        <p className="text-xs text-destructive">
          {(query.error as Error).message}
        </p>
      )}

      {!query.isLoading && artifacts.length === 0 && (
        <p className="text-xs text-muted-foreground">{t("artifacts.empty")}</p>
      )}

      {Object.entries(grouped).map(([kind, items]) => (
        <div key={kind} className="flex flex-col gap-2">
          <p className="text-[10px] font-medium uppercase text-muted-foreground">
            {kind} ({items.length})
          </p>
          <div className="grid gap-2">
            {items.map((artifact) => (
              <ArtifactCard
                key={artifact.id}
                runId={runId}
                artifact={artifact}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
