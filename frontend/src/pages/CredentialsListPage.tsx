import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import {
  CredentialFieldForm,
  type CredentialFieldValue,
} from "@/components/CredentialFieldForm";
import { OAuthConnectButton } from "@/components/OAuthConnectButton";
import type {
  CredentialCreate,
  CredentialListItem,
  CredentialOut,
  CredentialTypeSpec,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
const QK_TYPES = ["credentials", "types"] as const;
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

function emptyTypedValues(
  spec: CredentialTypeSpec | undefined,
): Record<string, CredentialFieldValue> {
  if (!spec) return {};
  const out: Record<string, CredentialFieldValue> = {};
  for (const f of spec.fields) {
    out[f.name] = {
      value: f.default != null ? String(f.default) : "",
      maskedFromServer: null,
    };
  }
  return out;
}

interface ModalProps {
  open: boolean;
  initialName?: string;
  initialDescription?: string;
  initialType?: string;
  initialFields?: FieldRow[];
  initialTypedValues?: Record<string, CredentialFieldValue>;
  credentialName: string;
  editingId: string | null;
  credentialTypes: CredentialTypeSpec[];
  onClose(): void;
  onSubmit(payload: CredentialCreate): Promise<void>;
  submitting: boolean;
  title: string;
}

function CredentialModal({
  open,
  initialName = "",
  initialDescription = "",
  initialType = "generic",
  initialFields,
  initialTypedValues,
  credentialName,
  editingId,
  credentialTypes,
  onClose,
  onSubmit,
  submitting,
  title,
}: ModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [credType, setCredType] = useState(initialType);
  const [rows, setRows] = useState<FieldRow[]>(
    initialFields && initialFields.length > 0
      ? initialFields
      : [{ key: "", value: "", maskedFromServer: null }],
  );
  const [typedValues, setTypedValues] = useState<
    Record<string, CredentialFieldValue>
  >(initialTypedValues ?? {});
  const [error, setError] = useState<string | null>(null);

  const typeSpec = useMemo(
    () => credentialTypes.find((ct) => ct.type === credType),
    [credentialTypes, credType],
  );
  const isGeneric = credType === "generic";
  const isOAuth = typeSpec?.auth.strategy === "oauth2";
  const connectApp = typeSpec?.auth.connect_app ?? null;

  useEffect(() => {
    setName(initialName);
    setDescription(initialDescription);
    setCredType(initialType);
    setRows(
      initialFields && initialFields.length > 0
        ? initialFields
        : [{ key: "", value: "", maskedFromServer: null }],
    );
    setTypedValues(initialTypedValues ?? emptyTypedValues(typeSpec));
    setError(null);
  }, [
    initialName,
    initialDescription,
    initialType,
    initialFields,
    initialTypedValues,
    typeSpec,
  ]);

  function onTypeChange(nextType: string) {
    setCredType(nextType);
    const spec = credentialTypes.find((ct) => ct.type === nextType);
    setTypedValues(emptyTypedValues(spec));
    if (nextType === "generic") {
      setRows([{ key: "", value: "", maskedFromServer: null }]);
    }
  }

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

  function updateTypedField(
    fieldName: string,
    patch: Partial<CredentialFieldValue>,
  ) {
    setTypedValues((prev) => ({
      ...prev,
      [fieldName]: { ...prev[fieldName], ...patch },
    }));
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
    if (isGeneric) {
      for (const r of rows) {
        const key = r.key.trim();
        if (!key) continue;
        if (editingId && !r.value && r.maskedFromServer) continue;
        fields[key] = r.value;
      }
    } else if (typeSpec) {
      for (const f of typeSpec.fields) {
        const row = typedValues[f.name];
        if (!row) continue;
        if (editingId && !row.value && row.maskedFromServer) continue;
        if (f.required && !row.value && !row.maskedFromServer) {
          setError(`${f.label || f.name} is required`);
          return;
        }
        if (row.value) fields[f.name] = row.value;
      }
    }

    try {
      await onSubmit({
        name: trimmedName,
        description: description.trim() || null,
        type: credType,
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
            <Label>{t("pages.credentials.typeLabel")}</Label>
            <Select
              value={credType}
              onValueChange={onTypeChange}
              disabled={!!editingId}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {credentialTypes.map((ct) => (
                  <SelectItem key={ct.type} value={ct.type}>
                    {ct.label || ct.type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isGeneric ? (
            <div className="grid gap-2">
              <Label>{t("pages.credentials.fieldsLabel")}</Label>
              <div className="space-y-2">
                {rows.map((row, i) => (
                  <div
                    key={i}
                    className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-2"
                  >
                    <Input
                      placeholder={t(
                        "pages.credentials.fieldNamePlaceholder",
                      )}
                      value={row.key}
                      onChange={(e) =>
                        updateRow(i, { key: e.target.value })
                      }
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
                      onChange={(e) =>
                        updateRow(i, { value: e.target.value })
                      }
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
                                  toTokenSnippet(
                                    effectiveName,
                                    row.key.trim(),
                                  ),
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
          ) : (
            <div className="grid gap-2">
              <Label>{t("pages.credentials.fieldsLabel")}</Label>
              <CredentialFieldForm
                fields={typeSpec?.fields ?? []}
                values={typedValues}
                onChange={updateTypedField}
                credentialName={effectiveName}
                editing={!!editingId}
              />
            </div>
          )}

          {isOAuth && connectApp && editingId && (
            <div className="grid gap-2 border-t pt-3">
              <p className="text-xs text-muted-foreground">
                {t("pages.credentials.oauthHint")}
              </p>
              <OAuthConnectButton
                connectApp={connectApp}
                credentialId={editingId}
              />
            </div>
          )}

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
  initialType: string;
  initialFields: FieldRow[];
  initialTypedValues: Record<string, CredentialFieldValue>;
}

export function CredentialsListPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [edit, setEdit] = useState<EditState | null>(null);

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: () => apiClient.credentials.list(),
  });

  const typesQuery = useQuery({
    queryKey: QK_TYPES,
    queryFn: () => apiClient.credentials.listTypes(),
  });

  const detailQuery = useQuery({
    queryKey: QK_DETAIL(edit?.credentialId ?? ""),
    queryFn: () => apiClient.credentials.get(edit!.credentialId!),
    enabled: edit?.mode === "edit" && !!edit.credentialId,
  });

  const credentialTypes = typesQuery.data ?? [];

  useEffect(() => {
    if (edit?.mode === "edit" && detailQuery.data) {
      const detail = detailQuery.data;
      const typeSpec = credentialTypes.find((ct) => ct.type === detail.type);
      setEdit((prev) => {
        if (!prev || prev.credentialId !== detail.id) return prev;
        if (detail.type === "generic" || !typeSpec) {
          const fields: FieldRow[] = detail.fields.map((f) => ({
            key: f.name,
            value: "",
            maskedFromServer: f.masked_value,
          }));
          return {
            ...prev,
            initialName: detail.name,
            initialDescription: detail.description ?? "",
            initialType: detail.type,
            initialFields:
              fields.length > 0
                ? fields
                : [{ key: "", value: "", maskedFromServer: null }],
            initialTypedValues: {},
          };
        }
        const typed: Record<string, CredentialFieldValue> = {};
        for (const f of typeSpec.fields) {
          const masked = detail.fields.find((mf) => mf.name === f.name);
          typed[f.name] = {
            value: "",
            maskedFromServer: masked?.masked_value ?? null,
          };
        }
        return {
          ...prev,
          initialName: detail.name,
          initialDescription: detail.description ?? "",
          initialType: detail.type,
          initialFields: [],
          initialTypedValues: typed,
        };
      });
    }
  }, [detailQuery.data, edit?.mode, credentialTypes]);

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
      initialType: "generic",
      initialFields: [{ key: "", value: "", maskedFromServer: null }],
      initialTypedValues: {},
    });
  }

  function onEdit(item: CredentialListItem) {
    setEdit({
      mode: "edit",
      credentialId: item.id,
      initialName: item.name,
      initialDescription: item.description ?? "",
      initialType: item.type,
      initialFields: item.field_names.map((n) => ({
        key: n,
        value: "",
        maskedFromServer: "\u2022\u2022\u2022\u2022",
      })),
      initialTypedValues: {},
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

  const typeLabelByName = useMemo(() => {
    const map = new Map<string, string>();
    for (const ct of credentialTypes) {
      map.set(ct.type, ct.label || ct.type);
    }
    return map;
  }, [credentialTypes]);

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
                  <TableHead>{t("pages.credentials.typeLabel")}</TableHead>
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
                      <TableCell className="text-xs text-muted-foreground">
                        {typeLabelByName.get(item.type) ?? item.type}
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
        initialType={edit?.initialType ?? "generic"}
        initialFields={edit?.initialFields}
        initialTypedValues={edit?.initialTypedValues}
        credentialTypes={credentialTypes}
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
