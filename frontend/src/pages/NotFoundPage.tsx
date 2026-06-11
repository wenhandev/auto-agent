import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { routePath } from "@/routes";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-baseline justify-between gap-4 border-b px-6 pb-3 pt-5">
        <div>
          <div className="text-xl font-semibold">{t("pages.notFound.title")}</div>
          <div className="text-xs text-muted-foreground">
            {t("pages.notFound.subtitle")}
          </div>
        </div>
      </div>
      <div className="flex-1 p-6">
        <div className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
          <div className="text-base font-medium text-foreground">
            {t("pages.notFound.emptyTitle")}
          </div>
          <Button asChild variant="outline">
            <Link to={routePath.workflows()}>{t("pages.notFound.backLink")}</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
