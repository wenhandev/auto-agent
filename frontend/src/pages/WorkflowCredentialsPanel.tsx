import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiClient, ApiError } from "@/api-platform";
import { routePath } from "@/routes";
import type { CredentialListItem } from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface Props {
  workflowId: string;
}

function tokenSnippet(name: string, field: string): string {
  return `{{cred.${name}.${field}}}`;
}

function copyToClipboard(text: string) {
  if (navigator.clipboard) {
    void navigator.clipboard.writeText(text);
  } else {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

const QK_LINKED = (workflowId: string) =>
  ["workflows", "credentials", workflowId] as const;
const QK_ALL = ["credentials", "list"] as const;

export function WorkflowCredentialsPanel({ workflowId }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const linkedQuery = useQuery({
    queryKey: QK_LINKED(workflowId),
    queryFn: () => apiClient.workflows.listCredentials(workflowId),
    enabled: !!workflowId,
  });

  const allQuery = useQuery({
    queryKey: QK_ALL,
    queryFn: () => apiClient.credentials.list(),
  });

  const linkMut = useMutation({
    mutationFn: (credentialId: string) =>
      apiClient.workflows.linkCredential(workflowId, credentialId),
    onSuccess: () => {
      setErrorMsg(null);
      setPickerOpen(false);
      void queryClient.invalidateQueries({ queryKey: QK_LINKED(workflowId) });
      void queryClient.invalidateQueries({ queryKey: QK_ALL });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        setErrorMsg(
          `${err.status}: ${String((err.body as { detail?: string })?.detail ?? err.message)}`,
        );
      } else {
        setErrorMsg(err instanceof Error ? err.message : String(err));
      }
    },
  });

  const unlinkMut = useMutation({
    mutationFn: (credentialId: string) =>
      apiClient.workflows.unlinkCredential(workflowId, credentialId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LINKED(workflowId) });
      void queryClient.invalidateQueries({ queryKey: QK_ALL });
    },
  });

  const linked = linkedQuery.data ?? [];
  const linkedIds = useMemo(
    () => new Set(linked.map((c) => c.id)),
    [linked],
  );
  const availableForPicker: CredentialListItem[] = useMemo(() => {
    const all = allQuery.data ?? [];
    return all.filter((c) => !linkedIds.has(c.id));
  }, [allQuery.data, linkedIds]);

  const globalEmpty = (allQuery.data ?? []).length === 0;

  return (
    <div className="flex flex-col gap-2 px-3 py-3">
      <div className="flex items-center gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t("pages.workflowDetail.credentialsSectionTitle")}
        </div>
        <Badge variant="secondary" className="px-2 py-0">
          {linked.length}
        </Badge>
        <div className="flex-1" />
        {!globalEmpty && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 px-2"
            disabled={availableForPicker.length === 0}
            title={
              availableForPicker.length === 0
                ? t("pages.workflowDetail.credentialsAllLinked")
                : ""
            }
            onClick={() => {
              setErrorMsg(null);
              setPickerOpen((v) => !v);
            }}
          >
            {t("pages.workflowDetail.credentialsAdd")}
          </Button>
        )}
      </div>

      {errorMsg && <div className="text-xs text-destructive">{errorMsg}</div>}

      {pickerOpen && availableForPicker.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border bg-muted/40 p-2">
          <div className="px-1 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t("pages.workflowDetail.credentialsPickerTitle")}
          </div>
          <div className="flex max-h-[140px] flex-col gap-1 overflow-auto">
            {availableForPicker.map((c) => (
              <button
                key={c.id}
                className="flex items-center justify-between gap-2 rounded-md border border-transparent px-2 py-1.5 text-left text-xs text-foreground transition-colors hover:border-border hover:bg-accent"
                onClick={() => linkMut.mutate(c.id)}
                disabled={linkMut.isPending}
              >
                <span className="font-medium">{c.name}</span>
                <span className="truncate text-muted-foreground">
                  {c.field_names.length > 0
                    ? c.field_names.join(", ")
                    : t("common.noFields")}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {linkedQuery.isLoading && (
        <div className="text-xs text-muted-foreground">
          {t("common.loading")}
        </div>
      )}

      {!linkedQuery.isLoading && linked.length === 0 && (
        <div className="text-xs">
          {globalEmpty ? (
            <>
              <div className="mb-2 text-muted-foreground">
                {t("pages.workflowDetail.credentialsEmptyGlobal")}
              </div>
              <Link
                to={routePath.credentials()}
                className="text-primary underline-offset-4 hover:underline"
              >
                {t("pages.workflowDetail.credentialsCreateFirst")}
              </Link>
            </>
          ) : (
            <div className="text-muted-foreground">
              {t("pages.workflowDetail.credentialsEmptyLinked")}
            </div>
          )}
        </div>
      )}

      {linked.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {linked.map((c) => (
            <li
              key={c.id}
              className="flex flex-col gap-1.5 rounded-md border bg-card p-2.5"
            >
              <div className="flex items-center gap-2">
                <span className="flex-1 text-sm font-semibold text-foreground">
                  {c.name}
                </span>
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-6 px-2 text-[11px]"
                  onClick={() => unlinkMut.mutate(c.id)}
                  disabled={
                    unlinkMut.isPending && unlinkMut.variables === c.id
                  }
                >
                  {t("pages.workflowDetail.credentialsRemove")}
                </Button>
              </div>
              {c.description && (
                <div className="text-[11px] text-muted-foreground">
                  {c.description}
                </div>
              )}
              <div className="flex flex-wrap gap-1">
                {c.field_names.length === 0 && (
                  <span className="text-[11px] text-muted-foreground">
                    {t("common.noFields")}
                  </span>
                )}
                {c.field_names.map((f) => (
                  <button
                    key={f}
                    type="button"
                    title={t("pages.workflowDetail.credentialsCopyToken")}
                    className="cursor-pointer rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-primary hover:text-foreground"
                    onClick={() => copyToClipboard(tokenSnippet(c.name, f))}
                  >
                    {tokenSnippet(c.name, f)}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
