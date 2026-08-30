import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiClient } from "@/api-platform";
import type { DesktopClientPolicy } from "@/types-platform";
import { WorkersPanel } from "@/components/WorkersPanel";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const QK_ORG_SETTINGS = ["orgs", "settings"] as const;

type SettingsWorkersTabProps = {
  orgId: string | undefined;
  canManageOrg: boolean;
};

export function SettingsWorkersTab({ orgId, canManageOrg }: SettingsWorkersTabProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const policyOptions: {
    value: DesktopClientPolicy;
    labelKey: string;
    descriptionKey: string;
  }[] = [
    {
      value: "approval_required",
      labelKey: "pages.settings.workersPolicyApprovalRequired",
      descriptionKey: "pages.settings.workersPolicyApprovalRequiredDesc",
    },
    {
      value: "open",
      labelKey: "pages.settings.workersPolicyOpen",
      descriptionKey: "pages.settings.workersPolicyOpenDesc",
    },
    {
      value: "disabled",
      labelKey: "pages.settings.workersPolicyDisabled",
      descriptionKey: "pages.settings.workersPolicyDisabledDesc",
    },
  ];

  const orgSettingsQuery = useQuery({
    queryKey: [...QK_ORG_SETTINGS, orgId],
    queryFn: () => apiClient.orgs.getSettings(orgId!),
    enabled: Boolean(orgId) && canManageOrg,
  });

  const orgSettingsMut = useMutation({
    mutationFn: (policy: DesktopClientPolicy) =>
      apiClient.orgs.updateSettings(orgId!, {
        desktop_client_policy: policy,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_ORG_SETTINGS });
      void queryClient.invalidateQueries({ queryKey: ["workers", "list"] });
    },
  });

  const activePolicy = orgSettingsQuery.data?.desktop_client_policy;
  const activeOption = policyOptions.find((o) => o.value === activePolicy);

  return (
    <div className="space-y-6">
      {canManageOrg && orgId && (
        <Card className="border-0 bg-card shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">
              {t("pages.settings.workersPolicyTitle")}
            </CardTitle>
            <CardDescription>
              {t("pages.settings.workersPolicyDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {orgSettingsQuery.isLoading && (
              <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
            )}
            {orgSettingsQuery.error && (
              <p className="text-sm text-destructive">
                {t("pages.settings.workersPolicyLoadError")}
              </p>
            )}
            {orgSettingsQuery.data && (
              <div className="grid max-w-md gap-2">
                <Label htmlFor="desktop-client-policy">
                  {t("pages.settings.workersPolicyLabel")}
                </Label>
                <Select
                  value={orgSettingsQuery.data.desktop_client_policy}
                  onValueChange={(v) =>
                    orgSettingsMut.mutate(v as DesktopClientPolicy)
                  }
                  disabled={orgSettingsMut.isPending}
                >
                  <SelectTrigger id="desktop-client-policy">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {policyOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {t(opt.labelKey)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {activeOption && (
                  <p className="text-xs text-muted-foreground">
                    {t(activeOption.descriptionKey)}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <WorkersPanel />
    </div>
  );
}
