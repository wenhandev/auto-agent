import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MonitorOff, MonitorPlay } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ImagePreviewDialog } from "@/components/ImagePreviewDialog";

interface StreamFrame {
  ts: string;
  seq: number;
  width: number;
  height: number;
  data: string;
}

interface Props {
  runId: string;
  active: boolean;
  /** Override WebSocket URL (desktop sidecar stream). */
  streamWsUrl?: string;
}

type StreamState =
  | "idle"
  | "connecting"
  | "waiting"
  | "live"
  | "ended"
  | "unavailable"
  | "headed";

export function LiveStreamPanel({ runId, active, streamWsUrl }: Props) {
  const { t } = useTranslation();
  const wsRef = useRef<WebSocket | null>(null);
  const frameSizeRef = useRef<{ w: number; h: number } | null>(null);
  const [state, setState] = useState<StreamState>("idle");
  const [frameSize, setFrameSize] = useState<{ w: number; h: number } | null>(
    null,
  );
  const [frameSrc, setFrameSrc] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    if (!active) {
      wsRef.current?.close();
      wsRef.current = null;
      frameSizeRef.current = null;
      setFrameSize(null);
      setFrameSrc(null);
      setState("idle");
      return;
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl =
      streamWsUrl ??
      `${proto}//${window.location.host}/ws/stream/${encodeURIComponent(runId)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setState("connecting");

    ws.onopen = () => {
      setState("connecting");
    };

    ws.onmessage = (msg) => {
      try {
        const payload = JSON.parse(msg.data as string) as {
          type?: string;
        } & Partial<StreamFrame>;
        if (payload.type === "stream_ended") {
          setState("ended");
          return;
        }
        if (payload.type === "stream_headed") {
          setState("headed");
          return;
        }
        if (payload.type === "stream_waiting") {
          setState("waiting");
          return;
        }
        if (payload.type === "stream_unavailable") {
          setState("unavailable");
          return;
        }
        if (payload.type === "frame" && payload.data) {
          const nextSrc = `data:image/jpeg;base64,${payload.data}`;
          setState("live");
          setFrameSrc(nextSrc);
          if (payload.width && payload.height && frameSizeRef.current === null) {
            const next = { w: payload.width, h: payload.height };
            frameSizeRef.current = next;
            setFrameSize(next);
          }
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      setState((prev) => (prev === "ended" ? "ended" : "unavailable"));
    };

    ws.onerror = () => {
      setState("unavailable");
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId, active, streamWsUrl]);

  const badgeLabel =
    state === "live"
      ? t("livestream.live")
      : state === "connecting"
        ? t("livestream.connecting")
        : state === "waiting"
          ? t("livestream.waiting")
          : state === "ended"
            ? t("livestream.ended")
            : state === "unavailable"
              ? t("livestream.unavailable")
              : state === "headed"
                ? t("livestream.headed")
                : t("livestream.idle");

  const canPreview = state === "live" && !!frameSrc;

  return (
    <>
      <div className="flex flex-col border-b">
        <div className="flex items-center gap-2 px-3 py-2">
          {state === "live" ? (
            <MonitorPlay className="h-3.5 w-3.5 text-green-500" />
          ) : (
            <MonitorOff className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <span className="text-xs font-medium">{t("livestream.title")}</span>
          <Badge variant="outline" className="ml-auto text-[10px]">
            {badgeLabel}
          </Badge>
        </div>
        <div className="relative aspect-video w-full bg-muted/40">
          {!active ? (
            <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-xs text-muted-foreground">
              {t("livestream.notRunning")}
            </div>
          ) : (
            <>
              <button
                type="button"
                className="absolute inset-0 flex items-center justify-center disabled:cursor-default"
                disabled={!canPreview}
                title={canPreview ? t("imagePreview.clickToEnlarge") : undefined}
                onClick={() => {
                  if (canPreview) setPreviewOpen(true);
                }}
              >
                {frameSrc ? (
                  <img
                    src={frameSrc}
                    alt={t("livestream.title")}
                    className={`h-full w-full object-contain ${canPreview ? "cursor-zoom-in" : ""}`}
                  />
                ) : (
                  <div className="h-full w-full" aria-hidden />
                )}
              </button>
              {(state === "connecting" || state === "waiting") && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/60 px-4 text-center text-xs text-muted-foreground">
                  {state === "waiting"
                    ? t("livestream.waitingHint")
                    : t("livestream.connecting")}
                </div>
              )}
              {state === "headed" && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/60 px-4 text-center text-xs text-muted-foreground">
                  {t("livestream.headedHint")}
                </div>
              )}
              {state === "unavailable" && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/60 px-4 text-center text-xs text-muted-foreground">
                  {t("livestream.unavailableHint")}
                </div>
              )}
            </>
          )}
        </div>
        {frameSize && active && state === "live" && (
          <div className="px-3 py-1 text-[10px] text-muted-foreground">
            {t("livestream.dimensions", {
              width: frameSize.w,
              height: frameSize.h,
            })}
          </div>
        )}
      </div>
      <ImagePreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        src={frameSrc}
        alt={t("livestream.title")}
        title={t("livestream.title")}
      />
    </>
  );
}
