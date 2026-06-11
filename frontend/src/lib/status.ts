import type { BadgeProps } from "@/components/ui/badge";

export type StatusName =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "aborted"
  | "idle";

export function statusBadgeVariant(status: string): BadgeProps["variant"] {
  switch (status) {
    case "running":
      return "info";
    case "completed":
      return "success";
    case "failed":
      return "destructive";
    case "aborted":
      return "warning";
    case "queued":
      return "secondary";
    default:
      return "outline";
  }
}
