import type { BadgeProps } from "@/components/ui/badge";

export type StatusName =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "aborted"
  | "rejected"
  | "idle";

export function statusBadgeVariant(status: string): BadgeProps["variant"] {
  switch (status) {
    case "running":
      return "info";
    case "completed":
      return "success";
    case "completed_with_errors":
      return "warning";
    case "failed":
      return "destructive";
    case "aborted":
    case "rejected":
      return "warning";
    case "queued":
      return "secondary";
    default:
      return "outline";
  }
}
