import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import { routePath } from "@/routes";
import type {
  WorkflowCreate,
  WorkflowListItem,
} from "@/types-platform";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { statusBadgeVariant } from "@/lib/status";

const QK_LIST = ["workflows", "list"] as const;

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

interface CreateModalProps {
  open: boolean;
  onClose(): void;
  onCreated(workflowId: string): void;
}

function CreateModal({ open, onClose, onCreated }: CreateModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const createMut = useMutation({
    mutationFn: (body: WorkflowCreate) => apiClient.workflows.create(body),
    onSuccess: (wf) => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
      onCreated(wf.id);
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
          : err instanceof Error
            ? err.message
            : String(err);
      setError(message);
    },
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError(t("pages.workflows.nameRequired"));
      return;
    }
    setError(null);
    createMut.mutate({
      name: name.trim(),
      description: description.trim() || null,
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setName("");
          setDescription("");
          setError(null);
          onClose();
        }
      }}
    >
      <DialogContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{t("pages.workflows.createModalTitle")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="wf-name">{t("pages.workflows.nameLabel")}</Label>
            <Input
              id="wf-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("pages.workflows.namePlaceholder")}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wf-desc">
              {t("pages.workflows.descriptionLabel")}
            </Label>
            <Textarea
              id="wf-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder={t("pages.workflows.descriptionPlaceholder")}
            />
          </div>
          {error && <div className="text-sm text-destructive">{error}</div>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={createMut.isPending}>
              {createMut.isPending
                ? t("common.creating")
                : t("common.create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface CardProps {
  item: WorkflowListItem;
  onOpen(): void;
  onDelete(): void;
  deleting: boolean;
}

function WorkflowCard({ item, onOpen, onDelete, deleting }: CardProps) {
  const { t } = useTranslation();
  const statusKey = item.last_run_status ?? null;
  return (
    <Card className="flex flex-col">
      <CardHeader className="space-y-1.5 pb-3">
        <CardTitle
          onClick={onOpen}
          className="cursor-pointer text-base hover:text-primary"
        >
          {item.name}
        </CardTitle>
        <CardDescription className="line-clamp-2 min-h-[2.5rem]">
          {item.description || t("pages.workflows.noDescription")}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 items-center justify-between pb-3 text-xs text-muted-foreground">
        <span>
          {statusKey ? (
            <Badge variant={statusBadgeVariant(statusKey)}>
              {t(`status.${statusKey}`, statusKey)}
            </Badge>
          ) : (
            <Badge variant="outline">{t("status.neverRun")}</Badge>
          )}
        </span>
        <span>{formatTime(item.updated_at)}</span>
      </CardContent>
      <CardFooter className="justify-end gap-2 pt-0">
        <Button size="sm" variant="outline" onClick={onOpen}>
          {t("common.open")}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={deleting}
          onClick={onDelete}
        >
          {deleting ? t("common.deleting") : t("common.delete")}
        </Button>
      </CardFooter>
    </Card>
  );
}

export function WorkflowsListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: () => apiClient.workflows.list(),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => apiClient.workflows.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_LIST });
    },
  });

  function onDelete(item: WorkflowListItem) {
    const ok = window.confirm(
      t("pages.workflows.confirmDelete", { name: item.name }),
    );
    if (!ok) return;
    deleteMut.mutate(item.id);
  }

  const items = listQuery.data ?? [];
  const isLoading = listQuery.isLoading;
  const error = listQuery.error;

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex items-baseline justify-between gap-4 border-b px-6 pb-3 pt-5">
        <div>
          <div className="text-xl font-semibold">
            {t("pages.workflows.title")}
          </div>
          <div className="text-xs text-muted-foreground">
            {t("pages.workflows.subtitle")}
          </div>
        </div>
        <Button onClick={() => setModalOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t("pages.workflows.newButton")}
        </Button>
      </div>
      <div className="flex-1 p-6">
        {error && (
          <div className="mb-3 text-sm text-destructive">
            {(error as Error).message}
          </div>
        )}
        {isLoading && (
          <div className="text-sm text-muted-foreground">
            {t("common.loading")}
          </div>
        )}
        {!isLoading && items.length === 0 && (
          <div className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
            <div className="text-base font-medium text-foreground">
              {t("pages.workflows.empty")}
            </div>
            <div className="text-sm">{t("pages.workflows.emptyHint")}</div>
            <Button onClick={() => setModalOpen(true)}>
              {t("pages.workflows.createCta")}
            </Button>
          </div>
        )}
        {!isLoading && items.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {items.map((item) => (
              <WorkflowCard
                key={item.id}
                item={item}
                onOpen={() => navigate(routePath.workflowDetail(item.id))}
                onDelete={() => onDelete(item)}
                deleting={
                  deleteMut.isPending && deleteMut.variables === item.id
                }
              />
            ))}
          </div>
        )}
      </div>
      <CreateModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={(id) => {
          setModalOpen(false);
          navigate(routePath.workflowDetail(id));
        }}
      />
    </div>
  );
}
