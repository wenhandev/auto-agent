import { Fragment, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import type {
  WebhookDeliveryOut,
  WebhookEventName,
  WebhookSubscriptionOut,
} from "@/types-platform";
import {
  clearV1ApiKey,
  ensureV1ApiKey,
  getV1ApiKey,
  setV1ApiKey,
} from "@/lib/v1ApiKey";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
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

const WEBHOOK_EVENTS: WebhookEventName[] = [
  "run_completed",
  "run_failed",
  "run_rejected",
  "run_aborted",
  "approval_requested",
];

const QK_WEBHOOKS = ["webhooks", "v1"] as const;

function formatError(err: unknown): string {
  return err instanceof ApiError
    ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
    : err instanceof Error
      ? err.message
      : String(err);
}

interface SubscriptionModalProps {
  open: boolean;
  editing: WebhookSubscriptionOut | null;
  apiKey: string;
  onClose(): void;
}

function SubscriptionModal({
  open,
  editing,
  apiKey,
  onClose,
}: SubscriptionModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [events, setEvents] = useState<WebhookEventName[]>(["run_completed"]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setUrl(editing?.url ?? "");
      setSecret("");
      setEnabled(editing?.enabled ?? true);
      setEvents(editing?.events?.length ? [...editing.events] : ["run_completed"]);
      setError(null);
    }
  }, [open, editing]);

  const saveMut = useMutation({
    mutationFn: async () => {
      if (editing) {
        return apiClient.webhooks.updateSubscriptionV1(apiKey, editing.id, {
          url: url.trim(),
          enabled,
          events,
          ...(secret.trim() ? { secret: secret.trim() } : {}),
        });
      }
      return apiClient.webhooks.createSubscriptionV1(apiKey, {
        url: url.trim(),
        events,
        enabled,
        ...(secret.trim() ? { secret: secret.trim() } : {}),
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_WEBHOOKS });
      onClose();
    },
    onError: (err: unknown) => setError(formatError(err)),
  });

  function toggleEvent(event: WebhookEventName) {
    setEvents((prev) =>
      prev.includes(event)
        ? prev.filter((e) => e !== event)
        : [...prev, event],
    );
  }

  function onSubmit() {
    if (!url.trim()) {
      setError(t("pages.settings.webhooksUrlRequired"));
      return;
    }
    if (events.length === 0) {
      setError(t("pages.settings.webhooksEventsRequired"));
      return;
    }
    saveMut.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {editing
              ? t("pages.settings.webhooksEditTitle")
              : t("pages.settings.webhooksCreateTitle")}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>{t("pages.settings.webhooksUrl")}</Label>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/hook"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>{t("pages.settings.webhooksEvents")}</Label>
            {WEBHOOK_EVENTS.map((event) => (
              <label
                key={event}
                className="flex cursor-pointer items-center gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  checked={events.includes(event)}
                  onChange={() => toggleEvent(event)}
                  className="rounded border"
                />
                {t(`pages.settings.webhookEvents.${event}`, event)}
              </label>
            ))}
          </div>
          <div className="flex items-center justify-between gap-4 rounded-md border px-3 py-2">
            <Label htmlFor="webhook-enabled">
              {t("pages.settings.webhooksEnabled")}
            </Label>
            <Switch
              id="webhook-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t("pages.settings.webhooksSecretLabel")}</Label>
            <Input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={
                editing
                  ? t("pages.settings.webhooksSecretKeep")
                  : t("pages.settings.webhooksSecretPlaceholder")
              }
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={onSubmit} disabled={saveMut.isPending}>
            {saveMut.isPending
              ? t("common.saving")
              : editing
                ? t("common.save")
                : t("common.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeliveriesRows({
  subscriptionId,
  apiKey,
}: {
  subscriptionId: string;
  apiKey: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const deliveriesQuery = useQuery({
    queryKey: ["webhooks", "deliveries", subscriptionId],
    queryFn: () =>
      apiClient.webhooks.listDeliveriesV1(apiKey, {
        subscriptionId,
        limit: 20,
      }),
  });

  const replayMut = useMutation({
    mutationFn: (deliveryId: string) =>
      apiClient.webhooks.replayDeliveryV1(apiKey, deliveryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["webhooks", "deliveries", subscriptionId],
      });
    },
  });

  const deliveries = deliveriesQuery.data ?? [];

  if (deliveriesQuery.isLoading) {
    return (
      <TableRow>
        <TableCell colSpan={5} className="text-xs text-muted-foreground">
          {t("common.loading")}
        </TableCell>
      </TableRow>
    );
  }

  if (deliveries.length === 0) {
    return (
      <TableRow>
        <TableCell colSpan={5} className="text-xs text-muted-foreground">
          {t("pages.settings.webhooksNoDeliveries")}
        </TableCell>
      </TableRow>
    );
  }

  return (
    <>
      {deliveries.map((d: WebhookDeliveryOut) => (
        <TableRow key={d.id} className="bg-muted/20">
          <TableCell className="font-mono text-xs">{d.event}</TableCell>
          <TableCell>
            <Badge
              variant={
                d.status === "delivered"
                  ? "default"
                  : d.status === "failed" || d.status === "exhausted"
                    ? "destructive"
                    : "secondary"
              }
            >
              {d.status}
            </Badge>
          </TableCell>
          <TableCell className="text-xs">
            {d.response_code ?? t("common.dash")}
          </TableCell>
          <TableCell className="text-xs text-muted-foreground">
            {new Date(d.created_at).toLocaleString()}
          </TableCell>
          <TableCell className="text-right">
            <Button
              variant="outline"
              size="sm"
              onClick={() => replayMut.mutate(d.id)}
              disabled={replayMut.isPending}
            >
              {t("pages.settings.webhooksReplay")}
            </Button>
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

export function WebhooksPanel() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [apiKey, setApiKeyState] = useState<string | null>(() => getV1ApiKey());
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WebhookSubscriptionOut | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const webhooksQuery = useQuery({
    queryKey: [...QK_WEBHOOKS, apiKey],
    queryFn: () => apiClient.webhooks.listSubscriptionsV1(apiKey!),
    enabled: !!apiKey,
    retry: false,
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) =>
      apiClient.webhooks.removeSubscriptionV1(apiKey!, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_WEBHOOKS });
    },
  });

  const testMut = useMutation({
    mutationFn: (id: string) =>
      apiClient.webhooks.testSubscriptionV1(apiKey!, id),
    onSuccess: (res) => {
      setTestMessage(
        t("pages.settings.webhooksTestQueued", { id: res.delivery_id }),
      );
    },
    onError: (err: unknown) => setTestMessage(formatError(err)),
  });

  function saveApiKey() {
    const key = apiKeyInput.trim();
    if (!key) return;
    setV1ApiKey(key);
    setApiKeyState(key);
    setApiKeyInput("");
  }

  function promptForKey() {
    const key = ensureV1ApiKey();
    if (key) setApiKeyState(key);
  }

  function openCreate() {
    const key = apiKey ?? ensureV1ApiKey();
    if (!key) return;
    if (!apiKey) setApiKeyState(key);
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(sub: WebhookSubscriptionOut) {
    setEditing(sub);
    setModalOpen(true);
  }

  function onDelete(sub: WebhookSubscriptionOut) {
    if (
      !window.confirm(
        t("pages.settings.webhooksConfirmDelete", { url: sub.url }),
      )
    ) {
      return;
    }
    deleteMut.mutate(sub.id);
  }

  const subscriptions = webhooksQuery.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="grid min-w-[240px] flex-1 gap-2">
          <Label htmlFor="v1-api-key">
            {t("pages.settings.webhooksApiKeyLabel")}
          </Label>
          <Input
            id="v1-api-key"
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder={
              apiKey
                ? t("pages.settings.webhooksApiKeyStored")
                : t("pages.settings.webhooksApiKeyPlaceholder")
            }
          />
        </div>
        <Button
          variant="outline"
          onClick={saveApiKey}
          disabled={!apiKeyInput.trim()}
        >
          {t("pages.settings.webhooksApiKeySave")}
        </Button>
        {!apiKey && (
          <Button variant="outline" onClick={promptForKey}>
            {t("pages.settings.webhooksApiKeyPrompt")}
          </Button>
        )}
        {apiKey && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              clearV1ApiKey();
              setApiKeyState(null);
            }}
          >
            {t("pages.settings.webhooksApiKeyClear")}
          </Button>
        )}
      </div>

      {!apiKey ? (
        <p className="text-sm text-muted-foreground">
          {t("pages.settings.webhooksApiKeyRequired")}
        </p>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void webhooksQuery.refetch()}
              disabled={webhooksQuery.isFetching}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              {t("pages.settings.webhooksRefresh")}
            </Button>
            <Button size="sm" onClick={openCreate}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              {t("pages.settings.webhooksCreate")}
            </Button>
          </div>

          {testMessage && (
            <p className="text-sm text-muted-foreground">{testMessage}</p>
          )}

          {webhooksQuery.error && (
            <div className="text-sm text-destructive">
              {formatError(webhooksQuery.error)}
            </div>
          )}

          {subscriptions.length === 0 && !webhooksQuery.error ? (
            <p className="text-sm text-muted-foreground">
              {t("pages.settings.webhooksEmpty")}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>{t("pages.settings.webhooksUrl")}</TableHead>
                  <TableHead>{t("pages.settings.webhooksEvents")}</TableHead>
                  <TableHead>{t("pages.settings.webhooksEnabled")}</TableHead>
                  <TableHead className="text-right">
                    {t("pages.settings.webhooksActions")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subscriptions.map((sub) => (
                  <Fragment key={sub.id}>
                    <TableRow>
                      <TableCell>
                        <button
                          type="button"
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() =>
                            setExpandedId(expandedId === sub.id ? null : sub.id)
                          }
                        >
                          {expandedId === sub.id ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </button>
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs">
                        {sub.url}
                      </TableCell>
                      <TableCell className="text-xs">
                        {sub.events.join(", ")}
                      </TableCell>
                      <TableCell>
                        <Badge variant={sub.enabled ? "default" : "secondary"}>
                          {sub.enabled
                            ? t("pages.settings.webhooksOn")
                            : t("pages.settings.webhooksOff")}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => testMut.mutate(sub.id)}
                            disabled={testMut.isPending}
                          >
                            <Send className="mr-1 h-3.5 w-3.5" />
                            {t("pages.settings.webhooksTest")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => openEdit(sub)}
                          >
                            {t("common.edit")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onDelete(sub)}
                            disabled={deleteMut.isPending}
                          >
                            <Trash2 className="mr-1 h-3.5 w-3.5" />
                            {t("common.delete")}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {expandedId === sub.id && apiKey && (
                      <>
                        <TableRow className="bg-muted/30">
                          <TableCell
                            colSpan={5}
                            className="py-2 text-xs font-medium"
                          >
                            {t("pages.settings.webhooksDeliveriesTitle")}
                          </TableCell>
                        </TableRow>
                        <DeliveriesRows
                          subscriptionId={sub.id}
                          apiKey={apiKey}
                        />
                      </>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}

      {apiKey && (
        <SubscriptionModal
          open={modalOpen}
          editing={editing}
          apiKey={apiKey}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}
