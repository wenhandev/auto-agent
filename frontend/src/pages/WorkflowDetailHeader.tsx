import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Play, Save, Square } from "lucide-react";
import { routePath } from "@/routes";
import { webPlatformPolicy } from "@/lib/webPlatformPolicy";
import type { PlatformRunStatus } from "@/platformStore";
import type { WorkflowVersionOut } from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { statusBadgeVariant } from "@/lib/status";
import { cn } from "@/lib/utils";

interface Props {
  name: string;
  onRename(newName: string): void;
  renameDisabled?: boolean;
  versions: WorkflowVersionOut[];
  currentVersionId: string | null;
  onSelectVersion(versionId: string): void;
  runStatus: PlatformRunStatus;
  onRun(): void;
  onAbort(): void;
  runDisabled: boolean;
  abortDisabled: boolean;
  isDirty?: boolean;
  onSave?(): void;
  saveDisabled?: boolean;
  isSaving?: boolean;
}

export function WorkflowDetailHeader({
  name,
  onRename,
  renameDisabled,
  versions,
  currentVersionId,
  onSelectVersion,
  runStatus,
  onRun,
  onAbort,
  runDisabled,
  abortDisabled,
  isDirty = false,
  onSave,
  saveDisabled = false,
  isSaving = false,
}: Props) {
  const { t } = useTranslation();
  const [draftName, setDraftName] = useState(name);

  useEffect(() => {
    setDraftName(name);
  }, [name]);

  function commitRename() {
    const trimmed = draftName.trim();
    if (!trimmed || trimmed === name) {
      setDraftName(name);
      return;
    }
    onRename(trimmed);
  }

  return (
    <div className="flex items-center gap-3 border-b bg-card/40 px-4 py-2">
      <input
        className={cn(
          "min-w-[220px] rounded-md border border-transparent bg-transparent px-2 py-1.5 text-base font-semibold text-foreground outline-none transition-colors",
          "hover:border-input hover:bg-accent/40",
          "focus:border-ring focus:bg-background focus:ring-2 focus:ring-ring/30",
          "disabled:opacity-50",
        )}
        value={draftName}
        onChange={(e) => setDraftName(e.target.value)}
        onBlur={commitRename}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            (e.target as HTMLInputElement).blur();
          } else if (e.key === "Escape") {
            setDraftName(name);
            (e.target as HTMLInputElement).blur();
          }
        }}
        disabled={renameDisabled}
        aria-label={t("pages.workflowDetail.nameAria")}
      />
      <Badge variant={statusBadgeVariant(runStatus)}>
        {t(`status.${runStatus}`, runStatus)}
      </Badge>
      {isDirty && (
        <Badge variant="outline" className="border-amber-500/50 text-amber-600">
          {t("pages.workflowDetail.unsaved")}
        </Badge>
      )}
      <div className="flex-1" />
      {versions.length > 0 && (
        <Select
          value={currentVersionId ?? ""}
          onValueChange={onSelectVersion}
        >
          <SelectTrigger
            className="h-8 w-[180px]"
            aria-label={t("pages.workflowDetail.versionAria")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {versions.map((v) => (
              <SelectItem key={v.id} value={v.id}>
                {t("pages.workflowDetail.versionLabel", {
                  index: v.version_index,
                  authored: v.authored_by,
                })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {webPlatformPolicy.showCloudCredentials && (
        <Button asChild variant="ghost" size="sm">
          <Link to={routePath.credentials()}>
            {t("pages.workflowDetail.credentialsLink")}
          </Link>
        </Button>
      )}
      {onSave && (
        <Button
          onClick={onSave}
          disabled={saveDisabled}
          size="sm"
          variant="secondary"
        >
          <Save className="mr-1.5 h-3.5 w-3.5" />
          {isSaving
            ? t("pages.workflowDetail.saving")
            : t("pages.workflowDetail.save")}
        </Button>
      )}
      <Button onClick={onRun} disabled={runDisabled} size="sm">
        <Play className="mr-1.5 h-3.5 w-3.5" />
        {t("pages.workflowDetail.run")}
      </Button>
      <Button
        onClick={onAbort}
        disabled={abortDisabled}
        size="sm"
        variant="destructive"
      >
        <Square className="mr-1.5 h-3.5 w-3.5" />
        {t("pages.workflowDetail.stop")}
      </Button>
    </div>
  );
}
