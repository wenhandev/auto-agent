import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Crosshair, Loader2, RefreshCw } from "lucide-react";
import { apiClient, ApiError } from "@/api-platform";
import type { SelectorCandidateOut } from "@/types-platform";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultUrl?: string;
  onApply: (selector: string) => void;
}

export function ElementPickerDialog({
  open,
  onOpenChange,
  defaultUrl = "",
  onApply,
}: Props) {
  const { t } = useTranslation();
  const imgRef = useRef<HTMLImageElement>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [pickerToken, setPickerToken] = useState<string | null>(null);
  const [url, setUrl] = useState(defaultUrl);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [viewport, setViewport] = useState<{ width: number; height: number } | null>(
    null,
  );
  const [candidates, setCandidates] = useState<SelectorCandidateOut[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const sessionsQuery = useQuery({
    queryKey: ["browser-sessions", "picker"],
    queryFn: () => apiClient.browserSessions.list(),
    enabled: open,
  });

  const liveSessions =
    sessionsQuery.data?.filter((s) => s.status === "live") ?? [];

  const refreshScreenshot = useCallback(async () => {
    if (!sessionId || !pickerToken) return;
    try {
      const { blob, viewport: vp } = await apiClient.browserSessions.screenshot(
        sessionId,
        pickerToken,
      );
      setViewport(vp);
      const next = URL.createObjectURL(blob);
      setImageUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return next;
      });
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : t("elementPicker.errorScreenshot"));
    }
  }, [sessionId, pickerToken, t]);

  const disablePicker = useCallback(async () => {
    if (sessionId && pickerToken) {
      try {
        await apiClient.browserSessions.pickerDisable(sessionId, pickerToken);
      } catch {
        // ignore cleanup errors
      }
    }
    setPickerToken(null);
  }, [sessionId, pickerToken]);

  useEffect(() => {
    if (!open) return;
    setUrl(defaultUrl);
    setError(null);
    setCandidates([]);
    setTestResult(null);
    setSelectedIdx(0);
  }, [open, defaultUrl]);

  useEffect(() => {
    if (!open) {
      void disablePicker();
      setImageUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }
    return () => {
      void disablePicker();
    };
  }, [open, disablePicker]);

  const startPicker = async (sid: string) => {
    setError(null);
    await disablePicker();
    setSessionId(sid);
    try {
      const enabled = await apiClient.browserSessions.pickerEnable(sid);
      setPickerToken(enabled.picker_token);
      if (url.trim()) {
        await apiClient.browserSessions.navigate(sid, enabled.picker_token, url.trim());
      }
      const { blob, viewport: vp } = await apiClient.browserSessions.screenshot(
        sid,
        enabled.picker_token,
      );
      setViewport(vp);
      setImageUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : t("elementPicker.errorStart"));
      setPickerToken(null);
    }
  };

  useEffect(() => {
    if (!open || sessionId || liveSessions.length === 0) return;
    void startPicker(liveSessions[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, liveSessions.length]);

  const navigateMut = useMutation({
    mutationFn: async () => {
      if (!sessionId || !pickerToken || !url.trim()) return;
      await apiClient.browserSessions.navigate(sessionId, pickerToken, url.trim());
      await refreshScreenshot();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? String(e.message) : t("elementPicker.errorNavigate")),
  });

  const handleImageClick = async (ev: React.MouseEvent<HTMLImageElement>) => {
    if (!sessionId || !pickerToken || !viewport || !imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * viewport.width;
    const y = ((ev.clientY - rect.top) / rect.height) * viewport.height;
    setPicking(true);
    setError(null);
    setTestResult(null);
    try {
      const result = await apiClient.browserSessions.pickElement(
        sessionId,
        pickerToken,
        x,
        y,
      );
      if (result.error) {
        setError(result.error);
        setCandidates([]);
        return;
      }
      setCandidates(result.candidates);
      setSelectedIdx(0);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : t("elementPicker.errorPick"));
    } finally {
      setPicking(false);
    }
  };

  const handleTest = async () => {
    const sel = candidates[selectedIdx]?.selector;
    if (!sessionId || !pickerToken || !sel) return;
    setTestResult(null);
    try {
      const result = await apiClient.browserSessions.testSelector(
        sessionId,
        pickerToken,
        sel,
      );
      setTestResult(
        t("elementPicker.testResult", {
          count: result.match_count,
          tag: result.preview?.tag ?? "?",
        }),
      );
    } catch (e) {
      setTestResult(e instanceof ApiError ? String(e.message) : t("elementPicker.errorTest"));
    }
  };

  const handleApply = () => {
    const sel = candidates[selectedIdx]?.selector;
    if (!sel) return;
    onApply(sel);
    onOpenChange(false);
  };

  const handleCreateSession = async () => {
    setError(null);
    try {
      const created = await apiClient.browserSessions.create({});
      await sessionsQuery.refetch();
      await startPicker(created.id);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : t("elementPicker.errorSession"));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Crosshair className="h-4 w-4" />
            {t("elementPicker.title")}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto]">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">{t("elementPicker.session")}</Label>
              <Select
                value={sessionId}
                onValueChange={(v) => void startPicker(v)}
                disabled={!liveSessions.length && !sessionId}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder={t("elementPicker.selectSession")} />
                </SelectTrigger>
                <SelectContent>
                  {liveSessions.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.id.slice(0, 8)}… ({s.status})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-end"
              onClick={() => void handleCreateSession()}
            >
              {t("elementPicker.newSession")}
            </Button>
          </div>

          <div className="flex gap-2">
            <Input
              className="h-8 text-xs font-mono"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={t("elementPicker.urlPlaceholder")}
            />
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={!pickerToken || navigateMut.isPending}
              onClick={() => navigateMut.mutate()}
            >
              {t("elementPicker.go")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={!pickerToken}
              onClick={() => void refreshScreenshot()}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>

          <p className="text-[11px] text-muted-foreground">{t("elementPicker.hint")}</p>

          <div className="relative overflow-hidden rounded-md border bg-muted/30">
            {imageUrl ? (
              <img
                ref={imgRef}
                src={imageUrl}
                alt={t("elementPicker.screenshotAlt")}
                className="max-h-[360px] w-full cursor-crosshair object-contain"
                onClick={(e) => void handleImageClick(e)}
              />
            ) : (
              <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
                {pickerToken ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                {t("elementPicker.noScreenshot")}
              </div>
            )}
            {picking && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/40">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            )}
          </div>

          {candidates.length > 0 && (
            <div className="flex flex-col gap-1">
              <Label className="text-xs">{t("elementPicker.candidates")}</Label>
              <div className="max-h-32 space-y-1 overflow-auto rounded border p-2">
                {candidates.map((c, i) => (
                  <button
                    key={`${c.strategy}-${c.selector}`}
                    type="button"
                    className={`flex w-full items-start gap-2 rounded px-2 py-1 text-left text-xs ${
                      i === selectedIdx ? "bg-primary/10 ring-1 ring-primary/30" : "hover:bg-muted"
                    }`}
                    onClick={() => setSelectedIdx(i)}
                  >
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      {c.strategy}
                    </Badge>
                    <span className="font-mono break-all">{c.selector}</span>
                    <span className="ml-auto shrink-0 text-muted-foreground">
                      ×{c.match_count}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {testResult && (
            <p className="text-xs text-muted-foreground">{testResult}</p>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={!candidates.length}
            onClick={() => void handleTest()}
          >
            {t("elementPicker.test")}
          </Button>
          <Button type="button" disabled={!candidates.length} onClick={handleApply}>
            {t("elementPicker.apply")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
