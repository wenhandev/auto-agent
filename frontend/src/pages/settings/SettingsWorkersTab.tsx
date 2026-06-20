import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

const DESKTOP_POLICY_OPTIONS: {
  value: DesktopClientPolicy;
  label: string;
  description: string;
}[] = [
  {
    value: "approval_required",
    label: "需要管理员批准",
    description: "新设备登录后需管理员批准才能执行任务（推荐）。",
  },
  {
    value: "open",
    label: "自动批准",
    description: "设备首次登录后自动批准（开发/小团队）。",
  },
  {
    value: "disabled",
    label: "禁用客户端",
    description: "禁止客户端登录与连接。",
  },
];

type SettingsWorkersTabProps = {
  orgId: string | undefined;
  canManageOrg: boolean;
};

export function SettingsWorkersTab({ orgId, canManageOrg }: SettingsWorkersTabProps) {
  const queryClient = useQueryClient();

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

  return (
    <div className="space-y-6">
      {canManageOrg && orgId && (
        <Card className="border-0 bg-card shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">客户端策略</CardTitle>
            <CardDescription>
              控制 Auto Agent Client 的注册与执行权限（仅管理员）。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {orgSettingsQuery.isLoading && (
              <p className="text-sm text-muted-foreground">加载中…</p>
            )}
            {orgSettingsQuery.error && (
              <p className="text-sm text-destructive">无法加载组织设置</p>
            )}
            {orgSettingsQuery.data && (
              <div className="grid max-w-md gap-2">
                <Label htmlFor="desktop-client-policy">策略</Label>
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
                    {DESKTOP_POLICY_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {
                    DESKTOP_POLICY_OPTIONS.find(
                      (o) => o.value === orgSettingsQuery.data!.desktop_client_policy,
                    )?.description
                  }
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <WorkersPanel />
    </div>
  );
}
