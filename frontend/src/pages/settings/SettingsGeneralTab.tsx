import { useTranslation } from "react-i18next";
import {
  LANGUAGE_LABEL,
  SUPPORTED_LANGUAGES,
  type SupportedLanguage,
} from "@/i18n";
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

export function SettingsGeneralTab() {
  const { t, i18n } = useTranslation();
  const currentLang = (i18n.resolvedLanguage ??
    i18n.language ??
    "en") as SupportedLanguage;

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle className="text-base">
          {t("pages.settings.languageSectionTitle")}
        </CardTitle>
        <CardDescription>
          {t("pages.settings.languageDescription")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid max-w-md gap-2">
          <Label htmlFor="language-select">
            {t("pages.settings.languageLabel")}
          </Label>
          <Select
            value={currentLang}
            onValueChange={(v) => void i18n.changeLanguage(v as SupportedLanguage)}
          >
            <SelectTrigger id="language-select" data-testid="lang-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SUPPORTED_LANGUAGES.map((lng) => (
                <SelectItem key={lng} value={lng}>
                  {LANGUAGE_LABEL[lng]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}
