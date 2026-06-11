import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Check,
  Clock,
  Copy,
  KeyRound,
  Plus,
  RefreshCw,
  Trash2,
  Webhook,
} from "lucide-react";

import { apiClient, ApiError } from "@/api-platform";
import type { TriggerCreate, TriggerOut, TriggerType } from "@/types-platform";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

interface Props {
  workflowId: string;
}

const QK_TRIGGERS = (workflowId: string) =>
  ["workflows", "triggers", workflowId] as const;

const CRON_RE = /^\s*[^\s]+\s+[^\s]+\s+[^\s]+\s+[^\s]+\s+[^\s]+\s*$/;

function isLikelyValidCron(value: string): boolean {
  return CRON_RE.test(value.trim());
}

function copyToClipboard(text: string): void {
  if (navigator.clipboard) {
    void navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

function buildCurlExample(t: TriggerOut, secret: string | null): string {
  const url = t.webhook_url ?? "";
  const s = secret ?? "<SECRET>";
  return `curl -X POST "${url}?secret=${s}" -H "Content-Type: application/json" -d '{}'`;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

interface NewTriggerForm {
  type: TriggerType;
  cron: string;
  path: string;
}

function emptyForm(): NewTriggerForm {
  return { type: "cron", cron: "", path: "" };
}

export function WorkflowTriggersPanel({ workflowId }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<NewTriggerForm>(emptyForm);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [revealedSecrets, setRevealedSecrets] = useState<Record<string, string>>(
    {},
  );
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const triggersQuery = useQuery({
    queryKey: QK_TRIGGERS(workflowId),
    queryFn: () => apiClient.triggers.list(workflowId),
    enabled: !!workflowId,
  });

  const triggers = triggersQuery.data ?? [];

  const createMut = useMutation({
    mutationFn: (body: TriggerCreate) =>
      apiClient.triggers.create(workflowId, body),
    onSuccess: (created) => {
      setErrorMsg(null);
      setCreateOpen(false);
      setForm(emptyForm());
      if (created.type === "webhook" && created.secret_full) {
        setRevealedSecrets((prev) => ({
          ...prev,
          [created.id]: created.secret_full!,
        }));
      }
      void queryClient.invalidateQueries({
        queryKey: QK_TRIGGERS(workflowId),
      });
    },
    onError: (err: unknown) => {
      setErrorMsg(formatApiError(err, t("triggers.createError")));
    },
  });

  const toggleEnabledMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiClient.triggers.update(id, { enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: QK_TRIGGERS(workflowId),
      });
    },
    onError: (err: unknown) => {
      setErrorMsg(formatApiError(err, t("triggers.updateError")));
    },
  });

  const regenerateMut = useMutation({
    mutationFn: (id: string) =>
      apiClient.triggers.update(id, { regenerate_secret: true }),
    onSuccess: (updated) => {
      if (updated.secret_full) {
        setRevealedSecrets((prev) => ({
          ...prev,
          [updated.id]: updated.secret_full!,
        }));
      }
      void queryClient.invalidateQueries({
        queryKey: QK_TRIGGERS(workflowId),
      });
    },
    onError: (err: unknown) => {
      setErrorMsg(formatApiError(err, t("triggers.updateError")));
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => apiClient.triggers.remove(id),
    onSuccess: (_data, id) => {
      setRevealedSecrets((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      void queryClient.invalidateQueries({
        queryKey: QK_TRIGGERS(workflowId),
      });
    },
    onError: (err: unknown) => {
      setErrorMsg(formatApiError(err, t("triggers.deleteError")));
    },
  });

  const canSubmit = useMemo(() => {
    if (form.type === "cron") return isLikelyValidCron(form.cron);
    return form.path === "" || /^[a-z0-9-]{3,64}$/.test(form.path);
  }, [form]);

  function onCopy(text: string, key: string): void {
    copyToClipboard(text);
    setCopiedKey(key);
    window.setTimeout(() => {
      setCopiedKey((curr) => (curr === key ? null : curr));
    }, 1200);
  }

  function submit(): void {
    setErrorMsg(null);
    if (form.type === "cron") {
      createMut.mutate({ type: "cron", schedule_or_path: form.cron.trim() });
    } else {
      createMut.mutate({
        type: "webhook",
        schedule_or_path: form.path.trim() || null,
      });
    }
  }

  return (
    <div
      className="flex flex-col gap-3 px-3 py-3"
      data-testid="workflow-triggers-panel"
    >
      <div className="flex items-center gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t("triggers.sectionTitle")}
        </div>
        <Badge variant="secondary" className="px-2 py-0">
          {triggers.length}
        </Badge>
        <div className="flex-1" />
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-2"
          onClick={() => {
            setForm(emptyForm());
            setErrorMsg(null);
            setCreateOpen(true);
          }}
          data-testid="triggers-new-button"
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          {t("triggers.newButton")}
        </Button>
      </div>

      {errorMsg && (
        <div className="text-xs text-destructive">
          {t("triggers.errorPrefix")} {errorMsg}
        </div>
      )}

      {triggersQuery.isLoading && (
        <div className="text-xs text-muted-foreground">
          {t("triggers.loading")}
        </div>
      )}

      {!triggersQuery.isLoading && triggers.length === 0 && (
        <div className="rounded-md border border-dashed bg-muted/30 p-3 text-xs">
          <div className="font-medium text-foreground">
            {t("triggers.emptyTitle")}
          </div>
          <div className="mt-1 text-muted-foreground">
            {t("triggers.emptyHint")}
          </div>
        </div>
      )}

      {triggers.length > 0 && (
        <ul className="flex flex-col gap-2">
          {triggers.map((trig) => (
            <li
              key={trig.id}
              className="flex flex-col gap-2 rounded-md border bg-card p-2.5"
              data-testid={`trigger-row-${trig.id}`}
              data-trigger-type={trig.type}
            >
              <div className="flex items-center gap-2">
                {trig.type === "cron" ? (
                  <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                ) : trig.type === "webhook" ? (
                  <Webhook className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <span
                  className="flex-1 truncate font-mono text-xs text-foreground"
                  title={trig.schedule_or_path}
                >
                  {trig.schedule_or_path}
                </span>
                <Switch
                  checked={trig.enabled}
                  onCheckedChange={(next) =>
                    toggleEnabledMut.mutate({ id: trig.id, enabled: next })
                  }
                  aria-label={t("triggers.enabledLabel")}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-1.5"
                  onClick={() => {
                    if (window.confirm(t("triggers.confirmDelete"))) {
                      deleteMut.mutate(trig.id);
                    }
                  }}
                  title={t("triggers.delete")}
                  data-testid={`trigger-delete-${trig.id}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>

              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <span>{t("triggers.lastFired")}:</span>
                <span>
                  {trig.last_fired_at
                    ? formatTimestamp(trig.last_fired_at)
                    : t("triggers.lastFiredNever")}
                </span>
              </div>

              {trig.type === "webhook" && (
                <WebhookSection
                  trigger={trig}
                  revealedSecret={revealedSecrets[trig.id] ?? null}
                  onCopy={onCopy}
                  copiedKey={copiedKey}
                  onRegenerate={() => regenerateMut.mutate(trig.id)}
                  regenerating={
                    regenerateMut.isPending && regenerateMut.variables === trig.id
                  }
                />
              )}
            </li>
          ))}
        </ul>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("triggers.newDialogTitle")}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="trigger-type">{t("triggers.typeLabel")}</Label>
              <Select
                value={form.type}
                onValueChange={(v: string) =>
                  setForm({ ...form, type: v as TriggerType })
                }
              >
                <SelectTrigger id="trigger-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cron">{t("triggers.typeCron")}</SelectItem>
                  <SelectItem value="webhook">
                    {t("triggers.typeWebhook")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {form.type === "cron" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="trigger-cron">{t("triggers.cronLabel")}</Label>
                <Input
                  id="trigger-cron"
                  placeholder={t("triggers.cronPlaceholder")}
                  value={form.cron}
                  onChange={(e) => setForm({ ...form, cron: e.target.value })}
                  className="font-mono"
                />
                <p className="text-[11px] text-muted-foreground">
                  {t("triggers.cronHelp")}
                </p>
                {form.cron && !isLikelyValidCron(form.cron) && (
                  <p className="text-[11px] text-destructive">
                    {t("triggers.cronInvalid")}
                  </p>
                )}
              </div>
            )}

            {form.type === "webhook" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="trigger-path">
                  {t("triggers.webhookPathLabel")}
                </Label>
                <Input
                  id="trigger-path"
                  placeholder={t("triggers.webhookPathPlaceholder")}
                  value={form.path}
                  onChange={(e) => setForm({ ...form, path: e.target.value })}
                  className="font-mono"
                />
                <p className="text-[11px] text-muted-foreground">
                  {t("triggers.webhookPathHelp")}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateOpen(false)}
            >
              {t("triggers.cancel")}
            </Button>
            <Button
              onClick={submit}
              disabled={!canSubmit || createMut.isPending}
            >
              {t("triggers.createCta")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface WebhookSectionProps {
  trigger: TriggerOut;
  revealedSecret: string | null;
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
  onRegenerate: () => void;
  regenerating: boolean;
}

function WebhookSection({
  trigger,
  revealedSecret,
  copiedKey,
  onCopy,
  onRegenerate,
  regenerating,
}: WebhookSectionProps) {
  const { t } = useTranslation();
  const fullUrl = trigger.webhook_url ?? "";
  const urlCopyKey = `url:${trigger.id}`;
  const curlCopyKey = `curl:${trigger.id}`;
  const secretDisplay = revealedSecret ?? trigger.secret_masked ?? "";

  return (
    <div className="flex flex-col gap-2 rounded-md bg-muted/30 p-2">
      <div className="flex items-center gap-2">
        <span className="w-[88px] text-[11px] uppercase tracking-wide text-muted-foreground">
          {t("triggers.webhookUrlLabel")}
        </span>
        <code
          className="flex-1 truncate rounded border bg-background px-1.5 py-1 font-mono text-[11px]"
          title={fullUrl}
          data-testid={`trigger-webhook-url-${trigger.id}`}
        >
          {fullUrl}
        </code>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5"
          onClick={() => onCopy(fullUrl, urlCopyKey)}
          title={t("triggers.copyUrl")}
          data-testid={`trigger-copy-url-${trigger.id}`}
        >
          {copiedKey === urlCopyKey ? (
            <Check className="h-3 w-3" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <span className="w-[88px] text-[11px] uppercase tracking-wide text-muted-foreground">
          {t("triggers.secretLabel")}
        </span>
        <code
          className="flex-1 truncate rounded border bg-background px-1.5 py-1 font-mono text-[11px]"
          title={secretDisplay}
        >
          {secretDisplay || "***"}
        </code>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5"
          onClick={() =>
            onCopy(buildCurlExample(trigger, revealedSecret), curlCopyKey)
          }
          title={t("triggers.copyCurl")}
        >
          {copiedKey === curlCopyKey ? (
            <Check className="h-3 w-3" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5"
          onClick={onRegenerate}
          disabled={regenerating}
          title={t("triggers.regenerateSecret")}
        >
          <RefreshCw className="h-3 w-3" />
        </Button>
      </div>

      {revealedSecret && (
        <div className="text-[11px] text-amber-600 dark:text-amber-400">
          {t("triggers.secretRevealed")}
        </div>
      )}
    </div>
  );
}

function formatApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const detail = (err.body as { detail?: string } | null)?.detail;
    return `${err.status}: ${detail ?? err.message}`;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

const _UnusedPencil = Pencil;
void _UnusedPencil;
