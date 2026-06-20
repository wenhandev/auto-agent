import { useTranslation } from "react-i18next";
import {
  Clock,
  Database,
  Filter,
  GitBranch,
  GitMerge,
  Globe,
  MousePointerClick,
  PenLine,
  ScanSearch,
  Sparkles,
  Split,
  Type,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store";
import {
  INSERTABLE_ACTION_TYPES,
  INSERTABLE_FLOW_TYPES,
  insertPaletteNodeAtSelection,
  type PaletteGroup,
  type PaletteNodeType,
} from "@/inspector/insertFlowNode";
import type { NodeType } from "@/types";

const GROUP_ORDER: PaletteGroup[] = ["browser", "flow", "data"];

const NODE_ICONS: Partial<Record<NodeType, typeof Globe>> = {
  navigate: Globe,
  click: MousePointerClick,
  fill: PenLine,
  wait: Clock,
  extract: ScanSearch,
  fuzzy_action: Sparkles,
  condition: GitBranch,
  switch: Split,
  set: Database,
  filter: Filter,
  merge: GitMerge,
};

function PaletteButton({
  entry,
  onClick,
}: {
  entry: PaletteNodeType;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  const Icon = NODE_ICONS[entry.type] ?? Type;

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-8 justify-start gap-2 px-2 text-xs"
      onClick={onClick}
    >
      <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      {t(`nodePalette.${entry.labelKey}`)}
    </Button>
  );
}

function insertPaletteNode(entry: PaletteNodeType, label: string): void {
  insertPaletteNodeAtSelection(entry, label);
}

export function NodePalette() {
  const { t } = useTranslation();
  const selectedEdgeId = useStore((s) => s.selectedEdgeId);
  const allEntries = [...INSERTABLE_ACTION_TYPES, ...INSERTABLE_FLOW_TYPES];

  return (
    <div className="absolute left-3 top-3 z-20 max-h-[calc(100%-1.5rem)] w-44 overflow-y-auto rounded-lg border bg-card/95 p-1.5 shadow-md backdrop-blur-sm">
      <div className="px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t("nodePalette.title")}
      </div>
      {selectedEdgeId ? (
        <div className="mx-1.5 mb-1 rounded-md border border-primary/30 bg-primary/5 px-2 py-1 text-[10px] leading-snug text-primary">
          {t("nodePalette.insertOnSelectedEdge")}
        </div>
      ) : null}
      {GROUP_ORDER.map((group) => {
        const entries = allEntries.filter((e) => e.group === group);
        if (entries.length === 0) return null;
        return (
          <div key={group} className="mt-1">
            <div className="px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground/80">
              {t(`nodePalette.group.${group}`)}
            </div>
            {entries.map((entry) => (
              <PaletteButton
                key={entry.type}
                entry={entry}
                onClick={() =>
                  insertPaletteNode(entry, t(`nodePalette.${entry.labelKey}`))
                }
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
