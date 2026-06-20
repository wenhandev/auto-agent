import { useTranslation } from "react-i18next";
import { WebhooksPanel } from "@/components/WebhooksPanel";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function SettingsWebhooksTab() {
  const { t } = useTranslation();

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle className="text-base">{t("pages.settings.webhooksTitle")}</CardTitle>
        <CardDescription>{t("pages.settings.webhooksDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        <WebhooksPanel />
      </CardContent>
    </Card>
  );
}
