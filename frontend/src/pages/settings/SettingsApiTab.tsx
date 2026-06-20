import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Copy, Plus, Trash2 } from "lucide-react";
import { apiClient } from "@/api-platform";
import { setV1ApiKey } from "@/lib/v1ApiKey";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const QK_API_KEYS = ["apiKeys", "list"] as const;

export function SettingsApiTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [apiKeyName, setApiKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  const apiKeysQuery = useQuery({
    queryKey: QK_API_KEYS,
    queryFn: () => apiClient.apiKeys.list(),
    retry: false,
  });

  const createKeyMut = useMutation({
    mutationFn: () => apiClient.apiKeys.create({ name: apiKeyName.trim() }),
    onSuccess: (result) => {
      setCreatedKey(result.key);
      setV1ApiKey(result.key);
      setApiKeyName("");
      void queryClient.invalidateQueries({ queryKey: QK_API_KEYS });
    },
  });

  const revokeKeyMut = useMutation({
    mutationFn: (keyId: string) => apiClient.apiKeys.remove(keyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_API_KEYS });
    },
  });

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle className="text-base">{t("pages.settings.apiKeysTitle")}</CardTitle>
        <CardDescription>{t("pages.settings.apiKeysDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {apiKeysQuery.error && (
          <div className="text-sm text-muted-foreground">
            {t("pages.settings.apiKeysUnavailable")}
          </div>
        )}
        {apiKeysQuery.data && apiKeysQuery.data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("pages.settings.apiKeysName")}</TableHead>
                <TableHead>{t("pages.settings.apiKeysPrefix")}</TableHead>
                <TableHead>{t("pages.settings.apiKeysCreated")}</TableHead>
                <TableHead className="text-right">
                  {t("pages.settings.apiKeysActions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {apiKeysQuery.data.map((key) => (
                <TableRow key={key.id}>
                  <TableCell>{key.name}</TableCell>
                  <TableCell>
                    <code className="font-mono text-xs">{key.prefix}…</code>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(key.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        if (
                          window.confirm(
                            t("pages.settings.apiKeysConfirmRevoke", {
                              name: key.name,
                            }),
                          )
                        ) {
                          revokeKeyMut.mutate(key.id);
                        }
                      }}
                      disabled={revokeKeyMut.isPending}
                    >
                      <Trash2 className="mr-1 h-3.5 w-3.5" />
                      {t("pages.settings.apiKeysRevoke")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {apiKeysQuery.data && apiKeysQuery.data.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {t("pages.settings.apiKeysEmpty")}
          </p>
        )}
        <div className="flex max-w-md items-end gap-2">
          <div className="grid flex-1 gap-2">
            <Label htmlFor="api-key-name">{t("pages.settings.apiKeysNewName")}</Label>
            <Input
              id="api-key-name"
              value={apiKeyName}
              onChange={(e) => setApiKeyName(e.target.value)}
              placeholder={t("pages.settings.apiKeysNewPlaceholder")}
            />
          </div>
          <Button
            onClick={() => createKeyMut.mutate()}
            disabled={!apiKeyName.trim() || createKeyMut.isPending}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {t("pages.settings.apiKeysCreate")}
          </Button>
        </div>
        {createdKey && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
            <p className="font-medium">{t("pages.settings.apiKeysCreatedTitle")}</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 break-all font-mono text-xs">{createdKey}</code>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void navigator.clipboard.writeText(createdKey)}
              >
                <Copy className="mr-1 h-3.5 w-3.5" />
                {t("pages.settings.apiKeysCopy")}
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {t("pages.settings.apiKeysCreatedHint")}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
