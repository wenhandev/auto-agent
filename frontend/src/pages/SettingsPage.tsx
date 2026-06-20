import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/auth/useAuth";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SettingsGeneralTab } from "@/pages/settings/SettingsGeneralTab";
import { SettingsLlmTab } from "@/pages/settings/SettingsLlmTab";
import { SettingsSecurityTab } from "@/pages/settings/SettingsSecurityTab";
import { SettingsWorkersTab } from "@/pages/settings/SettingsWorkersTab";
import { SettingsApiTab } from "@/pages/settings/SettingsApiTab";
import { SettingsWebhooksTab } from "@/pages/settings/SettingsWebhooksTab";

const SETTINGS_TABS = [
  "general",
  "llm",
  "security",
  "workers",
  "api",
  "webhooks",
] as const;

type SettingsTab = (typeof SETTINGS_TABS)[number];

function isSettingsTab(value: string | null): value is SettingsTab {
  return SETTINGS_TABS.includes(value as SettingsTab);
}

function canManageOrgSettings(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin";
}

export function SettingsPage() {
  const { t } = useTranslation();
  const { user, bypass } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const canManageOrg = bypass || canManageOrgSettings(user?.role);
  const orgId = user?.current_org_id;

  const rawTab = searchParams.get("tab");
  const activeTab: SettingsTab = isSettingsTab(rawTab) ? rawTab : "general";

  function onTabChange(next: string) {
    setSearchParams({ tab: next }, { replace: true });
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex items-baseline justify-between gap-4 border-b px-6 pb-3 pt-5">
        <div>
          <div className="text-xl font-semibold">{t("pages.settings.title")}</div>
          <div className="text-xs text-muted-foreground">
            {t("pages.settings.subtitle")}
          </div>
        </div>
      </div>

      <div className="p-6">
        <Tabs value={activeTab} onValueChange={onTabChange} className="gap-4">
          <TabsList className="h-auto w-fit flex-wrap">
            <TabsTrigger value="general">
              {t("pages.settings.tabGeneral")}
            </TabsTrigger>
            <TabsTrigger value="llm">{t("pages.settings.tabLlm")}</TabsTrigger>
            <TabsTrigger value="security">
              {t("pages.settings.tabSecurity")}
            </TabsTrigger>
            <TabsTrigger value="workers">
              {t("pages.settings.tabWorkers")}
            </TabsTrigger>
            <TabsTrigger value="api">{t("pages.settings.tabApi")}</TabsTrigger>
            <TabsTrigger value="webhooks">
              {t("pages.settings.tabWebhooks")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="general">
            <SettingsGeneralTab />
          </TabsContent>
          <TabsContent value="llm">
            <SettingsLlmTab />
          </TabsContent>
          <TabsContent value="security">
            <SettingsSecurityTab />
          </TabsContent>
          <TabsContent value="workers">
            <SettingsWorkersTab orgId={orgId} canManageOrg={canManageOrg} />
          </TabsContent>
          <TabsContent value="api">
            <SettingsApiTab />
          </TabsContent>
          <TabsContent value="webhooks">
            <SettingsWebhooksTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
