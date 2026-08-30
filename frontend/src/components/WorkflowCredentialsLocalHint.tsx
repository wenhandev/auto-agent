import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { routePath } from "@/routes";

export function WorkflowCredentialsLocalHint() {
  const { t } = useTranslation();

  return (
    <div className="space-y-2 px-3 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("pages.workflowDetail.credentialsSectionTitle")}
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("webPlatform.credentialsLocalHint")}
      </p>
      <Link
        to={routePath.clientDownload()}
        className="text-xs font-medium text-primary hover:underline"
      >
        {t("webPlatform.desktopOnly.downloadCta")}
      </Link>
    </div>
  );
}
