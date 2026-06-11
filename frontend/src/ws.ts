import { useStore } from "./store";
import type { RunEvent, Workflow } from "./types";

export function startRun(workflow: Workflow): WebSocket {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${window.location.host}/ws/run`);

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: "start", workflow }));
  };

  ws.onmessage = (msg) => {
    try {
      const frame = JSON.parse(msg.data) as RunEvent;
      useStore.getState().applyEvent(frame);
    } catch (err) {
      console.error("ws frame parse failed", err, msg.data);
    }
  };

  ws.onerror = (err) => {
    console.error("ws error", err);
  };

  ws.onclose = () => {
    if (useStore.getState().runStatus === "running") {
      useStore.getState().setRunStatus("completed");
    }
  };

  return ws;
}
