import { useTranslation } from "react-i18next";
import { ExternalLink, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  captchaKindLabel,
  type CaptchaKind,
  type CaptchaRunState,
} from "@/lib/captchaUtils";

interface Props {
  state: CaptchaRunState;
  onOpenApproval?: () => void;
}

export function CaptchaLiveBanner({ state, onOpenApproval }: Props) {
  const { t } = useTranslation();

  if (!state.showBanner) return null;

  const kindLabel = captchaKindLabel(state.kind, (key, fallback) =>
    t(key, fallback ?? key),
  );

  return (
    <div className="border-b border-amber-500/40 bg-amber-500/10 px-3 py-2.5">
      <div className="flex items-start gap-2">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">
              {t("captcha.liveBannerTitle")}
            </span>
            {state.kind && (
              <Badge variant="outline" className="text-[10px]">
                {kindLabel}
              </Badge>
            )}
            {state.awaitingApproval && (
              <Badge className="bg-amber-600 text-[10px] text-white hover:bg-amber-600">
                {t("captcha.awaitingApproval")}
              </Badge>
            )}
          </div>
          <p className="text-xs text-amber-900/90 dark:text-amber-100/90">
            {state.awaitingApproval
              ? t("captcha.liveBannerAwaiting")
              : t("captcha.liveBannerDetected")}
          </p>
          {state.awaitingApproval && onOpenApproval && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 border-amber-500/50 bg-background/60 text-xs"
              onClick={onOpenApproval}
            >
              <ExternalLink className="mr-1.5 h-3 w-3" />
              {t("captcha.openApproval")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export type { CaptchaKind, CaptchaRunState };
