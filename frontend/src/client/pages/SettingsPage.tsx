import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useDesktopAuth } from "../DesktopAuthContext";
import {
  fetchComputerUseSettings,
  fetchLlmSettings,
  saveComputerUseSettings,
  saveLlmSettings,
} from "../api";
import type { ComputerUseSettings } from "../api";
import type { LlmSettings } from "../types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { SettingsGeneralTab } from "@/pages/settings/SettingsGeneralTab";
import { SettingsRouteSkillsTab } from "@/pages/settings/SettingsRouteSkillsTab";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function DesktopSettingsPage() {
  const { t } = useTranslation();
  const { session, updateProfile } = useDesktopAuth();
  const [displayName, setDisplayName] = useState(session?.displayName ?? "");
  const [tagsText, setTagsText] = useState((session?.tags ?? []).join(", "));
  const [saved, setSaved] = useState(false);
  const [llm, setLlm] = useState<LlmSettings>({
    llm_provider: "google",
    gemini_provider: "vertex",
    google_model: "gemini-2.0-flash",
    gcp_location: "global",
  });
  const [llmSaved, setLlmSaved] = useState(false);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [computerUse, setComputerUse] = useState<ComputerUseSettings | null>(null);
  const [allowApp, setAllowApp] = useState("");
  const [cuError, setCuError] = useState<string | null>(null);

  useEffect(() => {
    void fetchLlmSettings()
      .then((cfg) => setLlm((prev) => ({ ...prev, ...cfg })))
      .catch(() => {
        // sidecar may not expose settings yet
      });
    void fetchComputerUseSettings()
      .then(setComputerUse)
      .catch(() => {
        // sidecar may not expose settings yet
      });
  }, []);

  function onSave(e: React.FormEvent) {
    e.preventDefault();
    const tags = tagsText
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    updateProfile({ displayName: displayName.trim() || displayName, tags });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  async function onSaveLlm(e: React.FormEvent) {
    e.preventDefault();
    setLlmError(null);
    try {
      const next = await saveLlmSettings(llm);
      setLlm(next);
      setLlmSaved(true);
      window.setTimeout(() => setLlmSaved(false), 2000);
    } catch (err) {
      setLlmError(err instanceof Error ? err.message : String(err));
    }
  }

  const provider = llm.llm_provider ?? "google";
  const geminiProvider = llm.gemini_provider ?? "ai_studio";

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {t("desktop.settings.title")}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t("desktop.settings.subtitle")}
        </p>
      </div>

      <SettingsGeneralTab />

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="text-base">
            {t("desktop.settings.deviceProfileTitle")}
          </CardTitle>
          <CardDescription>
            {t("desktop.settings.deviceProfileDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSave} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="display-name">
                {t("desktop.settings.displayName")}
              </Label>
              <Input
                id="display-name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tags">{t("desktop.settings.tags")}</Label>
              <Input
                id="tags"
                value={tagsText}
                onChange={(e) => setTagsText(e.target.value)}
                placeholder={t("desktop.settings.tagsPlaceholder")}
              />
            </div>
            <Button type="submit">
              {saved ? t("desktop.settings.saved") : t("common.save")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="text-base">
            {t("desktop.settings.localLlmTitle")}
          </CardTitle>
          <CardDescription>
            {t("desktop.settings.localLlmDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => void onSaveLlm(e)} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>{t("desktop.settings.provider")}</Label>
              <Select
                value={provider}
                onValueChange={(v) => setLlm((prev) => ({ ...prev, llm_provider: v }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="google">
                    {t("desktop.settings.providerGoogle")}
                  </SelectItem>
                  <SelectItem value="openai">
                    {t("desktop.settings.providerOpenai")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {provider === "google" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label>{t("desktop.settings.geminiProvider")}</Label>
                  <Select
                    value={geminiProvider}
                    onValueChange={(v) =>
                      setLlm((prev) => ({ ...prev, gemini_provider: v }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ai_studio">
                        {t("desktop.settings.geminiAiStudio")}
                      </SelectItem>
                      <SelectItem value="vertex">
                        {t("desktop.settings.geminiVertex")}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="google-model">{t("desktop.settings.model")}</Label>
                  <Input
                    id="google-model"
                    value={llm.google_model ?? ""}
                    onChange={(e) =>
                      setLlm((prev) => ({ ...prev, google_model: e.target.value }))
                    }
                  />
                </div>
                {geminiProvider === "vertex" ? (
                  <>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="gcp-project">
                        {t("desktop.settings.gcpProject")}
                      </Label>
                      <Input
                        id="gcp-project"
                        value={llm.gcp_project ?? ""}
                        onChange={(e) =>
                          setLlm((prev) => ({ ...prev, gcp_project: e.target.value }))
                        }
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="gcp-location">
                        {t("desktop.settings.gcpLocation")}
                      </Label>
                      <Input
                        id="gcp-location"
                        value={llm.gcp_location ?? "global"}
                        onChange={(e) =>
                          setLlm((prev) => ({ ...prev, gcp_location: e.target.value }))
                        }
                      />
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="google-api-key">
                      {t("desktop.settings.googleApiKey")}
                    </Label>
                    <Input
                      id="google-api-key"
                      type="password"
                      value={llm.google_api_key ?? ""}
                      onChange={(e) =>
                        setLlm((prev) => ({ ...prev, google_api_key: e.target.value }))
                      }
                      placeholder={t("desktop.settings.googleApiKeyKeep")}
                    />
                  </div>
                )}
              </>
            )}

            {provider === "openai" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="openai-model">
                    {t("desktop.settings.openaiModel")}
                  </Label>
                  <Input
                    id="openai-model"
                    value={llm.openai_model ?? ""}
                    onChange={(e) =>
                      setLlm((prev) => ({ ...prev, openai_model: e.target.value }))
                    }
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="openai-api-key">
                    {t("desktop.settings.openaiApiKey")}
                  </Label>
                  <Input
                    id="openai-api-key"
                    type="password"
                    value={llm.openai_api_key ?? ""}
                    onChange={(e) =>
                      setLlm((prev) => ({ ...prev, openai_api_key: e.target.value }))
                    }
                  />
                </div>
              </>
            )}

            {llmError && <p className="text-sm text-destructive">{llmError}</p>}
            <Button type="submit">
              {llmSaved ? t("desktop.settings.saved") : t("desktop.settings.saveLlm")}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="text-base">
            {t("desktop.settings.computerUseTitle")}
          </CardTitle>
          <CardDescription>
            {t("desktop.settings.computerUseDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {computerUse ? (
            <>
              <p className="text-sm text-muted-foreground">
                {computerUse.system_permissions_hint}
              </p>
              <p className="text-sm">
                {computerUse.available
                  ? t("desktop.settings.computerUseAvailable")
                  : t("desktop.settings.computerUseUnavailable")}
              </p>
              {!computerUse.available && computerUse.reason ? (
                <p className="text-xs text-muted-foreground font-mono break-all">
                  {computerUse.reason}
                </p>
              ) : null}
              <div className="space-y-2">
                <Label>{t("desktop.settings.alwaysAllowedApps")}</Label>
                {computerUse.always_allowed.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {t("desktop.settings.noAlwaysAllowed")}
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {computerUse.always_allowed.map((appId) => (
                      <li
                        key={appId}
                        className="flex items-center justify-between gap-2 text-sm"
                      >
                        <span className="truncate font-mono">{appId}</span>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setCuError(null);
                            void saveComputerUseSettings({ revoke: appId })
                              .then(setComputerUse)
                              .catch((err) =>
                                setCuError(
                                  err instanceof Error ? err.message : String(err),
                                ),
                              );
                          }}
                        >
                          {t("desktop.settings.revokeApp")}
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const value = allowApp.trim();
                  if (!value) return;
                  setCuError(null);
                  void saveComputerUseSettings({ allow_always: value })
                    .then((next) => {
                      setComputerUse(next);
                      setAllowApp("");
                    })
                    .catch((err) =>
                      setCuError(
                        err instanceof Error ? err.message : String(err),
                      ),
                    );
                }}
              >
                <Input
                  value={allowApp}
                  onChange={(e) => setAllowApp(e.target.value)}
                  placeholder={t("desktop.settings.allowAppPlaceholder")}
                />
                <Button type="submit" variant="secondary">
                  {t("desktop.settings.allowApp")}
                </Button>
              </form>
              {cuError ? (
                <p className="text-sm text-destructive">{cuError}</p>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t("desktop.settings.computerUseLoading")}
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="text-base">
            {t("desktop.settings.deviceStatusTitle")}
          </CardTitle>
          <CardDescription>
            {t("desktop.settings.deviceStatusDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <Link to="/device">{t("desktop.settings.viewDeviceStatus")}</Link>
          </Button>
        </CardContent>
      </Card>

      <Separator />

      <SettingsRouteSkillsTab />
    </div>
  );
}
