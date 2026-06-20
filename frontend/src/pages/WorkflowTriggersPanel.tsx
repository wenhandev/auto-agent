import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Check,
  Clock,
  Copy,
  KeyRound,
  Pencil,
  Plus,
  Radio,
  RefreshCw,
  Trash2,
  Webhook,
} from "lucide-react";

import { IntegrationAppLabel } from "@/components/IntegrationAppLabel";
import { apiClient, ApiError } from "@/api-platform";
import type {
  IntegrationDescriptor,
  IntegrationTriggerSpec,
  TriggerCreate,
  TriggerOut,
  TriggerType,
} from "@/types-platform";
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
  pollApp: string;
  pollResource: string;
  pollOperation: string;
  pollCredential: string;
  pollDedupPath: string;
  pollInterval: string;
  appName: string;
  appTrigger: string;
  appCredential: string;
}

function emptyForm(): NewTriggerForm {
  return {
    type: "cron",
    cron: "",
    path: "",
    pollApp: "",
    pollResource: "",
    pollOperation: "",
    pollCredential: "",
    pollDedupPath: "id",
    pollInterval: "60",
    appName: "",
    appTrigger: "",
    appCredential: "",
  };
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

  const integrationsQuery = useQuery({
    queryKey: ["integrations", "catalogue"],
    queryFn: () => apiClient.integrations.list(),
  });

  const credentialsQuery = useQuery({
    queryKey: ["workflows", "credentials", workflowId],
    queryFn: () => apiClient.workflows.listCredentials(workflowId),
    enabled: !!workflowId,
  });

  const triggers = triggersQuery.data ?? [];
  const integrations = integrationsQuery.data ?? [];
  const credentialNames = (credentialsQuery.data ?? []).map((c) => c.name);

  const pollApps = integrations.filter((d) =>
    (d.triggers ?? []).some((tr) => tr.kind === "poll"),
  );
  const appWebhookApps = integrations.filter((d) =>
    (d.triggers ?? []).some((tr) => tr.kind === "webhook"),
  );

  function pollTriggersForApp(app: string): IntegrationTriggerSpec[] {
    const desc = integrations.find((d) => d.app === app);
    return (desc?.triggers ?? []).filter((tr) => tr.kind === "poll");
  }

  function appTriggersForApp(app: string): IntegrationTriggerSpec[] {
    const desc = integrations.find((d) => d.app === app);
    return (desc?.triggers ?? []).filter((tr) => tr.kind === "webhook");
  }

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
    if (form.type === "webhook") {
      return form.path === "" || /^[a-z0-9-]{3,64}$/.test(form.path);
    }
    if (form.type === "poll") {
      return (
        !!form.pollApp &&
        !!form.pollResource &&
        !!form.pollOperation &&
        !!form.pollCredential
      );
    }
    if (form.type === "app") {
      return !!form.appName && !!form.appTrigger && !!form.appCredential;
    }
    return false;
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
      return;
    }
    if (form.type === "webhook") {
      createMut.mutate({
        type: "webhook",
        schedule_or_path: form.path.trim() || null,
      });
      return;
    }
    if (form.type === "poll") {
      createMut.mutate({
        type: "poll",
        poll_app: form.pollApp,
        poll_resource: form.pollResource,
        poll_operation: form.pollOperation,
        poll_credential: form.pollCredential,
        poll_dedup_path: form.pollDedupPath.trim() || "id",
        min_poll_interval_s: Number(form.pollInterval) || 60,
      });
      return;
    }
    createMut.mutate({
      type: "app",
      app_name: form.appName,
      app_trigger: form.appTrigger,
      app_credential: form.appCredential,
    });
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
                ) : trig.type === "poll" ? (
                  <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
                ) : trig.type === "app" ? (
                  <Radio className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <span
                  className="flex-1 truncate font-mono text-xs text-foreground"
                  title={trig.schedule_or_path}
                >
                  {trig.type === "poll"
                    ? t("triggers.pollSummary", {
                        app: trig.poll_app ?? "?",
                        resource: trig.poll_resource ?? "?",
                        operation: trig.poll_operation ?? "?",
                      })
                    : trig.type === "app"
                      ? t("triggers.appSummary", {
                          app: trig.app_name ?? "?",
                          trigger: trig.app_trigger ?? "?",
                        })
                      : trig.schedule_or_path}
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

              {trig.type === "poll" && trig.poll_app && (
                <div className="rounded-md bg-muted/30 p-2 text-[11px] text-muted-foreground">
                  <div className="mb-1">
                    <IntegrationAppLabel app={trig.poll_app} />
                  </div>
                  <div>
                    {t("triggers.pollCredentialLabel")}:{" "}
                    <span className="font-mono text-foreground">
                      {trig.poll_credential}
                    </span>
                  </div>
                  <div>
                    {t("triggers.pollIntervalLabel")}:{" "}
                    {trig.min_poll_interval_s ?? 60}s
                  </div>
                </div>
              )}

              {trig.type === "app" && (
                <div className="rounded-md bg-muted/30 p-2 text-[11px] text-muted-foreground">
                  {trig.app_name && (
                    <div className="mb-1">
                      <IntegrationAppLabel app={trig.app_name} />
                    </div>
                  )}
                  {trig.app_callback_url && (
                    <div className="flex items-center gap-2">
                      <span className="shrink-0">
                        {t("triggers.appCallbackUrlLabel")}:
                      </span>
                      <code className="truncate font-mono text-[10px] text-foreground">
                        {trig.app_callback_url}
                      </code>
                    </div>
                  )}
                  {trig.subscription_status && (
                    <div>
                      {t("triggers.subscriptionStatusLabel")}:{" "}
                      {trig.subscription_status}
                    </div>
                  )}
                </div>
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
                  <SelectItem value="poll">{t("triggers.typePoll")}</SelectItem>
                  <SelectItem value="app">{t("triggers.typeApp")}</SelectItem>
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

            {form.type === "poll" && (
              <PollTriggerFields
                form={form}
                setForm={setForm}
                pollApps={pollApps}
                credentialNames={credentialNames}
                pollTriggersForApp={pollTriggersForApp}
              />
            )}

            {form.type === "app" && (
              <AppTriggerFields
                form={form}
                setForm={setForm}
                appWebhookApps={appWebhookApps}
                credentialNames={credentialNames}
                appTriggersForApp={appTriggersForApp}
              />
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

function PollTriggerFields({
  form,
  setForm,
  pollApps,
  credentialNames,
  pollTriggersForApp,
}: {
  form: NewTriggerForm;
  setForm: (next: NewTriggerForm) => void;
  pollApps: IntegrationDescriptor[];
  credentialNames: string[];
  pollTriggersForApp: (app: string) => IntegrationTriggerSpec[];
}) {
  const { t } = useTranslation();
  const triggers = form.pollApp ? pollTriggersForApp(form.pollApp) : [];
  const selected = triggers.find((tr) => tr.name === form.pollOperation);

  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label>{t("triggers.pollAppLabel")}</Label>
        <Select
          value={form.pollApp}
          onValueChange={(v) =>
            setForm({
              ...form,
              pollApp: v,
              pollResource: "",
              pollOperation: "",
              pollDedupPath: "id",
            })
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="slack" />
          </SelectTrigger>
          <SelectContent>
            {pollApps.map((d) => (
              <SelectItem key={d.app} value={d.app}>
                <IntegrationAppLabel app={d.app} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{t("triggers.pollOperationLabel")}</Label>
        <Select
          value={form.pollOperation}
          onValueChange={(v) => {
            const tr = triggers.find((item) => item.name === v);
            setForm({
              ...form,
              pollOperation: v,
              pollResource: tr?.resource ?? form.pollResource,
              pollDedupPath: tr?.dedup_path ?? form.pollDedupPath,
            });
          }}
          disabled={!form.pollApp}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {triggers.map((tr) => (
              <SelectItem key={tr.name} value={tr.name}>
                {tr.label ?? tr.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selected?.resource && (
        <p className="text-[11px] text-muted-foreground">
          {t("triggers.pollResourceLabel")}: {selected.resource}
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        <Label>{t("triggers.pollCredentialLabel")}</Label>
        <Select
          value={form.pollCredential}
          onValueChange={(v) => setForm({ ...form, pollCredential: v })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {credentialNames.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="poll-dedup">{t("triggers.pollDedupPathLabel")}</Label>
        <Input
          id="poll-dedup"
          value={form.pollDedupPath}
          onChange={(e) => setForm({ ...form, pollDedupPath: e.target.value })}
          className="font-mono"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="poll-interval">{t("triggers.pollIntervalLabel")}</Label>
        <Input
          id="poll-interval"
          type="number"
          min={60}
          value={form.pollInterval}
          onChange={(e) => setForm({ ...form, pollInterval: e.target.value })}
        />
      </div>
    </>
  );
}

function AppTriggerFields({
  form,
  setForm,
  appWebhookApps,
  credentialNames,
  appTriggersForApp,
}: {
  form: NewTriggerForm;
  setForm: (next: NewTriggerForm) => void;
  appWebhookApps: IntegrationDescriptor[];
  credentialNames: string[];
  appTriggersForApp: (app: string) => IntegrationTriggerSpec[];
}) {
  const { t } = useTranslation();
  const triggers = form.appName ? appTriggersForApp(form.appName) : [];

  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label>{t("triggers.appNameLabel")}</Label>
        <Select
          value={form.appName}
          onValueChange={(v) =>
            setForm({ ...form, appName: v, appTrigger: "" })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {appWebhookApps.map((d) => (
              <SelectItem key={d.app} value={d.app}>
                <IntegrationAppLabel app={d.app} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{t("triggers.appTriggerLabel")}</Label>
        <Select
          value={form.appTrigger}
          onValueChange={(v) => setForm({ ...form, appTrigger: v })}
          disabled={!form.appName}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {triggers.map((tr) => (
              <SelectItem key={tr.name} value={tr.name}>
                {tr.label ?? tr.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>{t("triggers.appCredentialLabel")}</Label>
        <Select
          value={form.appCredential}
          onValueChange={(v) => setForm({ ...form, appCredential: v })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {credentialNames.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
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
