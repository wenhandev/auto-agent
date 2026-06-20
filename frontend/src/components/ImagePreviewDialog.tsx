import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  src: string | null;
  alt?: string;
  title?: string;
}

export function ImagePreviewDialog({
  open,
  onOpenChange,
  src,
  alt = "",
  title,
}: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[95vh] max-w-[min(96vw,1200px)] gap-0 overflow-hidden border bg-background p-2 sm:p-4">
        <DialogTitle className="sr-only">{title || alt || "Preview"}</DialogTitle>
        {src ? (
          <img
            src={src}
            alt={alt}
            className="mx-auto max-h-[85vh] w-full object-contain"
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
