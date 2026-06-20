import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { TokenChip } from "./TokenChip";
import {
  insertAtSelection,
  parseTokenSegments,
  removeToken,
} from "./variableUtils";

interface TokenTextFieldProps {
  value: string;
  onChange: (value: string) => void;
  shapes: Record<string, unknown>;
  multiline?: boolean;
  placeholder?: string;
  className?: string;
  insertTokenRef?: React.MutableRefObject<((token: string) => void) | null>;
}

export function TokenTextField({
  value,
  onChange,
  shapes,
  multiline = false,
  placeholder,
  className,
  insertTokenRef,
}: TokenTextFieldProps) {
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const segments = parseTokenSegments(value);
  const hasTokens = segments.some((s) => s.type === "token");
  const [focused, setFocused] = useState(false);

  const insertToken = useCallback(
    (token: string) => {
      const el = inputRef.current;
      if (!el) {
        onChange(value + token);
        return;
      }
      const start = el.selectionStart ?? value.length;
      const end = el.selectionEnd ?? start;
      const result = insertAtSelection(value, token, start, end);
      onChange(result.value);
      requestAnimationFrame(() => {
        el.focus();
        el.setSelectionRange(result.cursor, result.cursor);
      });
    },
    [onChange, value],
  );

  useEffect(() => {
    if (insertTokenRef) {
      insertTokenRef.current = insertToken;
    }
    return () => {
      if (insertTokenRef) insertTokenRef.current = null;
    };
  }, [insertToken, insertTokenRef]);

  const handleRemoveToken = (raw: string) => {
    onChange(removeToken(value, raw));
  };

  if (!hasTokens) {
    const commonProps = {
      ref: inputRef as never,
      value,
      placeholder,
      className: cn("text-xs", className),
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        onChange(e.target.value),
      onFocus: () => setFocused(true),
      onBlur: () => setFocused(false),
    };

    if (multiline) {
      return (
        <Textarea
          {...commonProps}
          rows={3}
          onKeyDown={(e: KeyboardEvent<HTMLTextAreaElement>) => e.stopPropagation()}
        />
      );
    }
    return <Input {...commonProps} />;
  }

  return (
    <div
      className={cn(
        "rounded-md border border-input bg-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2",
        focused && "ring-2 ring-ring ring-offset-2",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-1 px-2 py-1.5">
        {segments.map((seg, index) => {
          if (seg.type === "token") {
            return (
              <TokenChip
                key={`${index}-${seg.raw}`}
                inner={seg.inner}
                raw={seg.raw}
                shapes={shapes}
                onRemove={() => handleRemoveToken(seg.raw)}
              />
            );
          }
          if (seg.value.length === 0 && index === segments.length - 1) {
            return null;
          }
          return (
            <span
              key={`${index}-text`}
              className="whitespace-pre-wrap font-mono text-xs text-foreground"
            >
              {seg.value}
            </span>
          );
        })}
      </div>
      {multiline ? (
        <Textarea
          ref={inputRef as never}
          value={value}
          placeholder={placeholder}
          className="min-h-[56px] border-0 bg-transparent text-xs focus-visible:ring-0 focus-visible:ring-offset-0"
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => e.stopPropagation()}
        />
      ) : (
        <Input
          ref={inputRef as never}
          value={value}
          placeholder={placeholder}
          className="border-0 bg-transparent text-xs focus-visible:ring-0 focus-visible:ring-offset-0"
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        />
      )}
    </div>
  );
}

export function stringifyParamValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return String(value);
}

export function coerceStringParam(value: string, kind: "string" | "number"): unknown {
  if (kind === "number") {
    if (value.includes("{{")) return value;
    const n = Number(value);
    if (value.trim() !== "" && !Number.isNaN(n)) return n;
    return value;
  }
  return value;
}
