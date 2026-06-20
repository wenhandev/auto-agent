import { useEffect, useState } from "react";
import { useDesktopAuth } from "../DesktopAuthContext";
import { fetchLlmSettings, saveLlmSettings } from "../api";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function DesktopSettingsPage() {
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

  useEffect(() => {
    void fetchLlmSettings()
      .then((cfg) => setLlm((prev) => ({ ...prev, ...cfg })))
      .catch(() => {
        // sidecar may not expose settings yet
      });
  }, []);

  function onSave(e: React.FormEvent) {
    e.preventDefault();
    const tags = tagsText
      .split(",")
      .map((t) => t.trim())
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
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Worker profile and local LLM configuration for client runs.
        </p>
      </div>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="text-base">Worker profile</CardTitle>
          <CardDescription>
            Shown in cloud Settings → Workers for this device.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSave} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="display-name">Display name</Label>
              <Input
                id="display-name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tags">Tags (comma-separated)</Label>
              <Input
                id="tags"
                value={tagsText}
                onChange={(e) => setTagsText(e.target.value)}
                placeholder="default, pool-a"
              />
            </div>
            <Button type="submit">{saved ? "Saved" : "Save"}</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="text-base">Local LLM</CardTitle>
          <CardDescription>
            Encrypted at rest in ~/.auto-agent-worker/llm.json (Fernet key in .key).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => void onSaveLlm(e)} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label>Provider</Label>
              <Select
                value={provider}
                onValueChange={(v) => setLlm((prev) => ({ ...prev, llm_provider: v }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="google">Google / Gemini</SelectItem>
                  <SelectItem value="openai">OpenAI</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {provider === "google" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label>Gemini provider</Label>
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
                      <SelectItem value="ai_studio">AI Studio (API key)</SelectItem>
                      <SelectItem value="vertex">Vertex AI</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="google-model">Model</Label>
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
                      <Label htmlFor="gcp-project">GCP project</Label>
                      <Input
                        id="gcp-project"
                        value={llm.gcp_project ?? ""}
                        onChange={(e) =>
                          setLlm((prev) => ({ ...prev, gcp_project: e.target.value }))
                        }
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="gcp-location">GCP location</Label>
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
                    <Label htmlFor="google-api-key">Google API key</Label>
                    <Input
                      id="google-api-key"
                      type="password"
                      value={llm.google_api_key ?? ""}
                      onChange={(e) =>
                        setLlm((prev) => ({ ...prev, google_api_key: e.target.value }))
                      }
                      placeholder="Leave blank to keep saved key"
                    />
                  </div>
                )}
              </>
            )}

            {provider === "openai" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="openai-model">Model</Label>
                  <Input
                    id="openai-model"
                    value={llm.openai_model ?? ""}
                    onChange={(e) =>
                      setLlm((prev) => ({ ...prev, openai_model: e.target.value }))
                    }
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="openai-api-key">OpenAI API key</Label>
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
            <Button type="submit">{llmSaved ? "Saved" : "Save LLM settings"}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
