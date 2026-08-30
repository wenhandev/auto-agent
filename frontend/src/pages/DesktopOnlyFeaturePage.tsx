import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";
import type { DesktopOnlyFeatureKey } from "@/lib/webPlatformPolicy";
import { routePath } from "@/routes";
import { Button } from "@/components/ui/button";

interface Props {
  featureKey: DesktopOnlyFeatureKey;
}

export function DesktopOnlyFeaturePage({ featureKey }: Props) {
  const { t } = useTranslation();

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-lg font-semibold">
        {t(`webPlatform.desktopOnly.${featureKey}.title`)}
      </h1>
      <p className="max-w-md text-sm text-muted-foreground">
        {t(`webPlatform.desktopOnly.${featureKey}.description`)}
      </p>
      <Button asChild variant="outline">
        <Link to={routePath.clientDownload()}>
          <Download className="mr-2 h-4 w-4" />
          {t("webPlatform.desktopOnly.downloadCta")}
        </Link>
      </Button>
    </div>
  );
}
