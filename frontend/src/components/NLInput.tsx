import "./NLInput.css";
import { useState } from "react";
import { generateWorkflow, getSampleWorkflow } from "../api";
import { useStore } from "../store";

const PLACEHOLDER =
  "\u6253\u5f00 https://example.com\uff0c\u7b49\u5f85 1 \u79d2\uff0c\u627e\u5230 h1 \u4e3b\u6807\u9898\uff0c\u7136\u540e\u8df3\u8f6c\u5230 https://example.org";

export function NLInput() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"generate" | "sample" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const setWorkflow = useStore((s) => s.setWorkflow);

  async function onGenerate() {
    setError(null);
    setBusy("generate");
    try {
      const wf = await generateWorkflow(text.trim() || PLACEHOLDER);
      setWorkflow(wf);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function onLoadSample() {
    setError(null);
    setBusy("sample");
    try {
      const wf = await getSampleWorkflow();
      setWorkflow(wf);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="nl-input">
      <div className="nl-input-row">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={PLACEHOLDER}
          disabled={busy !== null}
        />
        <div className="nl-input-buttons">
          <button
            className="primary"
            onClick={onGenerate}
            disabled={busy !== null}
          >
            {busy === "generate"
              ? "\u751f\u6210\u4e2d..."
              : "\u751f\u6210\u5de5\u4f5c\u6d41"}
          </button>
          <button onClick={onLoadSample} disabled={busy !== null}>
            {busy === "sample"
              ? "\u52a0\u8f7d\u4e2d..."
              : "\u52a0\u8f7d\u793a\u4f8b"}
          </button>
        </div>
      </div>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}
