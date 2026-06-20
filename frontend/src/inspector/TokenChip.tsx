import { useEffect, useRef, useState } from "react";
import { KeyRound, Variable, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { isChipToken, resolveTokenPreview } from "./variableUtils";

interface TokenChipProps {
  inner: string;
  raw: string;
  shapes: Record<string, unknown>;
  onRemove: () => void;
}

export function TokenChip({ inner, raw, shapes, onRemove }: TokenChipProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const prefix = inner.split(".", 1)[0];
  const preview = resolveTokenPreview(inner, shapes);
  const label = inner;

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  if (!isChipToken(inner)) {
    return (
      <Badge variant="outline" className="font-mono text-[10px]">
        {raw}
      </Badge>
    );
  }

  return (
    <div ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        className={cn(
          "inline-flex max-w-[220px] items-center gap-1 rounded-md border px-1.5 py-0.5",
          "bg-secondary/60 font-mono text-[10px] hover:bg-secondary",
        )}
        onClick={() => setOpen((v) => !v)}
        title={inner}
      >
        {prefix === "cred" ? (
          <KeyRound className="h-3 w-3 shrink-0 text-amber-600" />
        ) : (
          <Variable className="h-3 w-3 shrink-0 text-sky-600" />
        )}
        <span className="truncate">{label}</span>
        <span
          role="button"
          tabIndex={-1}
          className="ml-0.5 rounded p-0.5 hover:bg-muted"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          aria-label={t("nodeInspector.removeTokenAria")}
        >
          <X className="h-3 w-3" />
        </span>
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-max max-w-[280px] rounded-md border bg-popover p-2 text-xs shadow-md">
          <div className="mb-1 font-mono text-[10px] text-muted-foreground">
            {raw}
          </div>
          <div className="break-all font-mono">
            {preview ?? t("nodeInspector.tokenPreviewUnknown")}
          </div>
        </div>
      )}
    </div>
  );
}
