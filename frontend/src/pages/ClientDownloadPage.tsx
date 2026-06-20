import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Apple, Download, Laptop, Monitor, Workflow } from "lucide-react";
import { clientCloudUrlDefault, clientDownloadTargets } from "@/lib/client-downloads";
import { ROUTES } from "@/routes";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const PLATFORM_ICONS = {
  macos: Apple,
  windows: Monitor,
  linux: Laptop,
} as const;

export function ClientDownloadPage() {
  const { t } = useTranslation();
  const targets = clientDownloadTargets();
  const cloudUrl = clientCloudUrlDefault();

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-10">
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Workflow className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("clientDownload.title")}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("clientDownload.subtitle")}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {targets.map((target) => {
            const Icon = PLATFORM_ICONS[target.platform];
            return (
              <Card key={target.platform} className="flex flex-col">
                <CardHeader className="pb-2">
                  <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
                    <Icon className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <CardTitle className="text-base">{t(target.labelKey)}</CardTitle>
                  <CardDescription className="text-xs">
                    {t(target.hintKey)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="mt-auto pt-0">
                  {target.url ? (
                    <Button asChild className="w-full" variant="secondary">
                      <a href={target.url} target="_blank" rel="noreferrer">
                        <Download className="mr-2 h-4 w-4" />
                        {t("clientDownload.download")}
                      </a>
                    </Button>
                  ) : (
                    <Button className="w-full" variant="secondary" disabled>
                      {t("clientDownload.comingSoon")}
                    </Button>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("clientDownload.stepsTitle")}</CardTitle>
            <CardDescription>{t("clientDownload.stepsSubtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
              <li>{t("clientDownload.stepInstall")}</li>
              <li>
                {t("clientDownload.stepSignIn", { cloudUrl })}
              </li>
              <li>{t("clientDownload.stepApprove")}</li>
              <li>{t("clientDownload.stepRun")}</li>
            </ol>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button asChild variant="outline" size="sm">
                <Link to={ROUTES.login}>{t("clientDownload.openConsole")}</Link>
              </Button>
            </div>
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground">
          {t("clientDownload.buildFromSource")}{" "}
          <code className="rounded bg-muted px-1 py-0.5">client/README.md</code>
        </p>
      </div>
    </div>
  );
}
