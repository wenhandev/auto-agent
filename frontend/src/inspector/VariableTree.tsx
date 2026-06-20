import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ShapeTreeNode } from "./variableUtils";
import { tokenForPath } from "./variableUtils";

interface VariableTreeProps {
  nodeId: string;
  nodeLabel: string;
  tree: ShapeTreeNode[];
  onSelect: (token: string) => void;
  defaultOpen?: boolean;
}

function TreeNode({
  nodeId,
  item,
  depth,
  onSelect,
}: {
  nodeId: string;
  item: ShapeTreeNode;
  depth: number;
  onSelect: (token: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = !!item.children?.length;

  if (hasChildren) {
    return (
      <div className="flex flex-col">
        <button
          type="button"
          className={cn(
            "flex items-center gap-1 rounded px-1 py-0.5 text-left text-xs hover:bg-muted/60",
          )}
          style={{ paddingLeft: depth * 12 + 4 }}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          <span className="font-medium">{item.label}</span>
          <span className="truncate text-muted-foreground">{item.preview}</span>
        </button>
        {open &&
          item.children!.map((child) => (
            <TreeNode
              key={`${nodeId}.${child.path}`}
              nodeId={nodeId}
              item={child}
              depth={depth + 1}
              onSelect={onSelect}
            />
          ))}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-2 rounded px-1 py-0.5 text-left text-xs hover:bg-muted/60",
      )}
      style={{ paddingLeft: depth * 12 + 16 }}
      onClick={() => onSelect(tokenForPath(nodeId, item.path))}
      title={tokenForPath(nodeId, item.path)}
    >
      <span className="font-medium">{item.label}</span>
      <span className="truncate text-muted-foreground">{item.preview}</span>
    </button>
  );
}

export function VariableTree({
  nodeId,
  nodeLabel,
  tree,
  onSelect,
  defaultOpen = true,
}: VariableTreeProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);

  if (tree.length === 0) return null;

  return (
    <div className="rounded-md border bg-muted/20">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs font-semibold hover:bg-muted/40"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        <span className="font-mono">{nodeId}</span>
        <span className="truncate font-normal text-muted-foreground">
          {nodeLabel}
        </span>
      </button>
      {open && (
        <div className="border-t pb-1 pt-0.5">
          {tree.map((item) => (
            <TreeNode
              key={`${nodeId}.${item.path}`}
              nodeId={nodeId}
              item={item}
              depth={0}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
      <div className="border-t px-2 py-1 text-[10px] text-muted-foreground">
        {t("nodeInspector.variablesCopyHint")}
      </div>
    </div>
  );
}

interface VariableTreeListProps {
  predecessors: Array<{ id: string; label: string; tree: ShapeTreeNode[] }>;
  onSelect: (token: string) => void;
}

export function VariableTreeList({
  predecessors,
  onSelect,
}: VariableTreeListProps) {
  return (
    <div className="flex flex-col gap-2">
      {predecessors.map((pred) => (
        <VariableTree
          key={pred.id}
          nodeId={pred.id}
          nodeLabel={pred.label}
          tree={pred.tree}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

interface VariableInsertMenuProps {
  predecessors: Array<{ id: string; label: string; tree: ShapeTreeNode[] }>;
  onInsert: (token: string) => void;
  disabled?: boolean;
}

export function VariableInsertMenu({
  predecessors,
  onInsert,
  disabled,
}: VariableInsertMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  if (predecessors.length === 0) {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-[10px]"
        disabled
      >
        {t("nodeInspector.insertVariable")}
      </Button>
    );
  }

  return (
    <div className="relative">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-7 px-2 text-[10px]"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        {t("nodeInspector.insertVariable")}
      </Button>
      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute right-0 top-full z-50 mt-1 w-[300px] max-h-64 overflow-auto rounded-md border bg-popover p-2 shadow-md">
            <VariableTreeList
              predecessors={predecessors}
              onSelect={(token) => {
                onInsert(token);
                setOpen(false);
              }}
            />
          </div>
        </>
      )}
    </div>
  );
}
