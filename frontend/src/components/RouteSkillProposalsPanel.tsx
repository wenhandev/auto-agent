import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, X } from "lucide-react";
import { apiClient } from "@/api-platform";
import type { RouteSkillProposalAdoptPreviewOut } from "@/types-platform";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const proposalsQueryKey = (sourceType: string, sourceId: string) =>
  ["route-skill-proposals", sourceType, sourceId] as const;

interface Props {
  sourceType: string;
  sourceId: string;
  enabled?: boolean;
  emptyHint?: string;
  compact?: boolean;
}

export function RouteSkillProposalsPanel({
  sourceType,
  sourceId,
  enabled = true,
  emptyHint,
  compact = false,
}: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [expandedProposalId, setExpandedProposalId] = useState<string | null>(
    null,
  );
  const [adoptPreview, setAdoptPreview] =
    useState<RouteSkillProposalAdoptPreviewOut | null>(null);

  const proposalsQuery = useQuery({
    queryKey: proposalsQueryKey(sourceType, sourceId),
    queryFn: () =>
      apiClient.routeSkillProposals.list({
        source_type: sourceType,
        source_id: sourceId,
      }),
    enabled: enabled && !!sourceId,
  });

  const adoptMut = useMutation({
    mutationFn: (proposalId: string) =>
      apiClient.routeSkillProposals.adopt(proposalId),
    onSuccess: () => {
      setAdoptPreview(null);
      void queryClient.invalidateQueries({
        queryKey: proposalsQueryKey(sourceType, sourceId),
      });
      void queryClient.invalidateQueries({ queryKey: ["route-skills"] });
    },
  });

  const dismissMut = useMutation({
    mutationFn: (proposalId: string) =>
      apiClient.routeSkillProposals.dismiss(proposalId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: proposalsQueryKey(sourceType, sourceId),
      });
    },
  });

  async function onAdoptClick(proposalId: string) {
    const preview = await apiClient.routeSkillProposals.adoptPreview(proposalId);
    if (preview.will_create_new) {
      adoptMut.mutate(proposalId);
      return;
    }
    setAdoptPreview(preview);
  }

  const proposals = proposalsQuery.data ?? [];
  const pendingProposals = proposals.filter((p) => p.status === "pending");

  return (
    <>
      <div className={cn(!compact && "border-b px-6 py-4")}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium">
            {t("recordings.proposalsTitle")}
          </h2>
          {proposalsQuery.isLoading && (
            <span className="text-xs text-muted-foreground">
              {t("common.loading")}
            </span>
          )}
        </div>
        {pendingProposals.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {emptyHint ?? t("recordings.proposalsEmpty")}
          </p>
        ) : (
          <div className="space-y-3">
            {pendingProposals.map((proposal) => (
              <div
                key={proposal.id}
                className="rounded-md border bg-card/40 p-3 text-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">
                      {proposal.capability}{" "}
                      <span className="text-muted-foreground">
                        · {proposal.domain}
                      </span>
                    </div>
                    <div className="mt-1 font-mono text-xs text-muted-foreground">
                      {proposal.url_pattern}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        setExpandedProposalId(
                          expandedProposalId === proposal.id
                            ? null
                            : proposal.id,
                        )
                      }
                    >
                      {expandedProposalId === proposal.id
                        ? t("recordings.proposalsHide")
                        : t("recordings.proposalsPreview")}
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => void onAdoptClick(proposal.id)}
                      disabled={adoptMut.isPending}
                    >
                      <Check className="mr-1.5 h-3.5 w-3.5" />
                      {t("recordings.proposalsAdopt")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => dismissMut.mutate(proposal.id)}
                      disabled={dismissMut.isPending}
                    >
                      <X className="mr-1.5 h-3.5 w-3.5" />
                      {t("recordings.proposalsDismiss")}
                    </Button>
                  </div>
                </div>
                {expandedProposalId === proposal.id && (
                  <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted/40 p-2 text-xs">
                    {proposal.prompt}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog
        open={adoptPreview !== null}
        onOpenChange={(open) => {
          if (!open) setAdoptPreview(null);
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("recordings.adoptMergeTitle")}</DialogTitle>
            <DialogDescription>
              {t("recordings.adoptMergeDescription")}
            </DialogDescription>
          </DialogHeader>
          {adoptPreview?.existing_route_skill && (
            <p className="text-xs text-muted-foreground">
              {t("recordings.adoptMergeExisting", {
                pattern: adoptPreview.existing_route_skill.url_pattern,
              })}
            </p>
          )}
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-muted/40 p-3 text-xs">
            {adoptPreview?.merged_prompt}
          </pre>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdoptPreview(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => {
                if (adoptPreview) adoptMut.mutate(adoptPreview.proposal.id);
              }}
              disabled={adoptMut.isPending}
            >
              {t("recordings.adoptMergeConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
