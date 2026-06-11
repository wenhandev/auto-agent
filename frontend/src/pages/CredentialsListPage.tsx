import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import type {
  CredentialCreate,
  CredentialListItem,
  CredentialOut,
} from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const QK_LIST = ["credentials", "list"] as const;
const QK_DETAIL = (id: string) => ["credentials", "detail", id] as const;

interface FieldRow {
  key: string;
  value: string;
  maskedFromServer: string | null;
}

function toTokenSnippet(name: string, field: string): string {
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

interface ModalProps {
  open: boolean;
  initialName?: string;
  initialDescription?: string;
  initialFields?: FieldRow[];
  credentialName: string;
  editingId: string | null;
  onClose(): void;
  onSubmit(payload: CredentialCreate): Promise<void>;
  submitting: boolean;
  title: string;
}

function CredentialModal({
  open,
  initialName = "",
  initialDescription = "",
  initialFields,
  credentialName,
  editingId,
  onClose,
  onSubmit,
  submitting,
  title,
}: ModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [rows, setRows] = useState<FieldRow[]>(
    initialFields && initialFields.length > 0
      ? initialFields
      : [{ key: "", value: "", maskedFromServer: null }],
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(initialName);
    setDescription(initialDescription);
    setRows(
      initialFields && initialFields.length > 0
        ? initialFields
        : [{ key: "", value: "", maskedFromServer: null }],
    );
    setError(null);
  }, [initialName, initialDescription, initialFields]);

  function updateRow(idx: number, patch: Partial<FieldRow>) {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }

  function addRow() {
    setRows((prev) => [
      ...prev,
      { key: "", value: "", maskedFromServer: null },
    ]);
  }

  function removeRow(idx: number) {
    setRows((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError(t("pages.credentials.nameRequired"));
      return;
    }
    const fields: Record<string, string> = {};
    for (const r of rows) {
      const key = r.key.trim();
      if (!key) continue;
      if (editingId && !r.value && r.maskedFromServer) {
        continue;
      }
      fields[key] = r.value;
    }
    try {
      await onSubmit({
        name: trimmedName,
        description: description.trim() || null,
        fields,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const effectiveName = name.trim() || credentialName || "cred-name";

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DialogContent className="max-w-2xl">
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="cred-name">
              {t("pages.credentials.nameLabel")}
            </Label>
            <Input
              id="cred-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="cred-desc">
              {t("pages.credentials.descriptionLabel")}
            </Label>
            <Input
              id="cred-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label>{t("pages.credentials.fieldsLabel")}</Label>
            <div className="space-y-2">
              {rows.map((row, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-2"
                >
                  <Input
                    placeholder={t("pages.credentials.fieldNamePlaceholder")}
                    value={row.key}
                    onChange={(e) => updateRow(i, { key: e.target.value })}
                  />
                  <Input
                    placeholder={
                      editingId && row.maskedFromServer
                        ? t("pages.credentials.keepValue", {
                            masked: row.maskedFromServer,
                          })
                        : t("pages.credentials.valuePlaceholder")
                    }
                    value={row.value}
                    onChange={(e) => updateRow(i, { value: e.target.value })}
                    type="password"
                  />
                  <div className="min-w-[120px]">
                    {row.key.trim() && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            className="cursor-pointer rounded border bg-muted px-2 py-1 font-mono text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
                            onClick={() =>
                              copyToClipboard(
                                toTokenSnippet(effectiveName, row.key.trim()),
                              )
                            }
                          >
                            {toTokenSnippet(effectiveName, row.key.trim())}
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>
                          {t("pages.workflowDetail.credentialsCopyToken")}
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeRow(i)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              onClick={addRow}
            >
              {t("pages.credentials.addRow")}
            </Button>
          </div>
          {error && <div className="text-sm text-destructive">{error}</div>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("common.saving") : t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface EditState {
  mode: "create" | "edit";
  credentialId: string | null;
  initialName: string;
  initialDescription: string;
  initialFields: FieldRow[];
}

export function CredentialsListPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [edit, setEdit] = useState<EditState | null>(null);

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: () => apiClient.credentials.list(),
  });

  const detailQuery = useQuery({
    queryKey: QK_DETAIL(edit?.credentialId ?? ""),
    queryFn: () => apiClient.credentials.get(edit!.credentialId!),
    enabled: edit?.mode === "edit" && !!edit.credentialId,
  });

  useEffect(() => {
    if (edit?.mode === "edit" && detailQuery.data) {
      setEdit((prev) => {
        if (!prev || prev.credentialId !== detailQuery.data!.id) return prev;
        const fields: FieldRow[] = detailQuery.data!.fields.map((f) => ({
          key: f.name,
          value: "",
          maskedFromServer: f.masked_value,
        }));
        return {
          ...prev,
          initialName: detailQuery.data!.name,
          initialDescription: detailQuery.data!.description ?? "",
          initialFields:
            fields.length > 0
              ? fields
              : [{ key: "", value: "", maskedFromServer: null }],
        };
      });
    }
  }, [detailQuery.data, edit?.mode]);

  const createMut = useMutation({
    mutationFn: (body: CredentialCreate) =>
      apiClient.credentials.create(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
    },
  });

  const updateMut = useMutation({
    mutationFn: (args: { id: string; body: CredentialCreate }) =>
      apiClient.credentials.update(args.id, args.body),
    onSuccess: (data: CredentialOut) => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
      void queryClient.invalidateQueries({ queryKey: QK_DETAIL(data.id) });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => apiClient.credentials.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
    },
  });

  function onCreate() {
    setEdit({
      mode: "create",
      credentialId: null,
      initialName: "",
      initialDescription: "",
      initialFields: [{ key: "", value: "", maskedFromServer: null }],
    });
  }

  function onEdit(item: CredentialListItem) {
    setEdit({
      mode: "edit",
      credentialId: item.id,
      initialName: item.name,
      initialDescription: item.description ?? "",
      initialFields: item.field_names.map((n) => ({
        key: n,
        value: "",
        maskedFromServer: "\u2022\u2022\u2022\u2022",
      })),
    });
  }

  function onDelete(item: CredentialListItem) {
    const ok = window.confirm(
      t("pages.credentials.confirmDelete", { name: item.name }),
    );
    if (!ok) return;
    deleteMut.mutate(item.id);
  }

  async function handleSubmit(body: CredentialCreate) {
    if (edit?.mode === "create") {
      await createMut.mutateAsync(body);
    } else if (edit?.mode === "edit" && edit.credentialId) {
      await updateMut.mutateAsync({ id: edit.credentialId, body });
    }
    setEdit(null);
  }

  const items = listQuery.data ?? [];
  const error = listQuery.error;

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex items-baseline justify-between gap-4 border-b px-6 pb-3 pt-5">
        <div>
          <div className="text-xl font-semibold">
            {t("pages.credentials.title")}
          </div>
          <div className="text-xs text-muted-foreground">
            {t("pages.credentials.subtitle")}
          </div>
        </div>
        <Button onClick={onCreate}>
          <Plus className="mr-2 h-4 w-4" />
          {t("pages.credentials.newButton")}
        </Button>
      </div>
      <div className="flex-1 p-6">
        {error && (
          <div className="mb-3 text-sm text-destructive">
            {(error as ApiError).message ?? String(error)}
          </div>
        )}
        {listQuery.isLoading && (
          <div className="text-sm text-muted-foreground">
            {t("common.loading")}
          </div>
        )}
        {!listQuery.isLoading && items.length === 0 && (
          <div className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
            <div className="text-base font-medium text-foreground">
              {t("pages.credentials.empty")}
            </div>
            <Button onClick={onCreate}>
              {t("pages.credentials.newButton")}
            </Button>
          </div>
        )}
        {!listQuery.isLoading && items.length > 0 && (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("pages.credentials.table.name")}</TableHead>
                  <TableHead>
                    {t("pages.credentials.table.description")}
                  </TableHead>
                  <TableHead>{t("pages.credentials.table.fields")}</TableHead>
                  <TableHead>{t("pages.credentials.table.updated")}</TableHead>
                  <TableHead className="w-0" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => {
                  const used = (item.usage_count ?? 0) > 0;
                  return (
                    <TableRow key={item.id}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <span>{item.name}</span>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span
                                className={cn(
                                  "inline-flex h-5 min-w-[20px] cursor-help items-center justify-center rounded-full border px-1.5 text-[11px]",
                                  used
                                    ? "border-primary bg-primary/20 text-primary"
                                    : "text-muted-foreground",
                                )}
                              >
                                {item.usage_count ?? 0}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              {used
                                ? t("pages.credentials.usageTooltipUsed", {
                                    count: item.usage_count ?? 0,
                                  })
                                : t("pages.credentials.usageTooltipUnused")}
                            </TooltipContent>
                          </Tooltip>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {item.description ?? t("common.dash")}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1.5">
                          {item.field_names.map((f) => (
                            <Tooltip key={f}>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  className="cursor-pointer rounded border bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
                                  onClick={() =>
                                    copyToClipboard(
                                      toTokenSnippet(item.name, f),
                                    )
                                  }
                                >
                                  {toTokenSnippet(item.name, f)}
                                </button>
                              </TooltipTrigger>
                              <TooltipContent>
                                {t("pages.workflowDetail.credentialsCopyToken")}
                              </TooltipContent>
                            </Tooltip>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(item.updated_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onEdit(item)}
                          >
                            {t("common.edit")}
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => onDelete(item)}
                            disabled={
                              deleteMut.isPending &&
                              deleteMut.variables === item.id
                            }
                          >
                            {t("common.delete")}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
      <CredentialModal
        open={edit !== null}
        editingId={edit?.credentialId ?? null}
        credentialName={edit?.initialName ?? ""}
        initialName={edit?.initialName ?? ""}
        initialDescription={edit?.initialDescription ?? ""}
        initialFields={edit?.initialFields}
        onClose={() => setEdit(null)}
        onSubmit={handleSubmit}
        submitting={createMut.isPending || updateMut.isPending}
        title={
          edit?.mode === "create"
            ? t("pages.credentials.createTitle")
            : t("pages.credentials.editTitle")
        }
      />
    </div>
  );
}
