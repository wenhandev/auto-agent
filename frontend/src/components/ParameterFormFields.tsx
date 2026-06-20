import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { WorkflowParameter } from "@/types";

interface Props {
  parameters: WorkflowParameter[];
  values: Record<string, unknown>;
  onChange(name: string, value: unknown): void;
  disabled?: boolean;
}

interface FileParamValue {
  file?: File;
  file_id?: string;
  filename?: string;
  bytes?: number;
}

function defaultFor(param: WorkflowParameter): unknown {
  if (param.default !== undefined && param.default !== null) {
    return param.default;
  }
  switch (param.type) {
    case "boolean":
      return false;
    case "number":
      return "";
    case "json":
      return "{}";
    case "file":
      return null;
    default:
      return "";
  }
}

export function ParameterFormFields({
  parameters,
  values,
  onChange,
  disabled,
}: Props) {
  const { t } = useTranslation();

  if (!parameters.length) {
    return (
      <p className="text-sm text-muted-foreground">
        {t("runDialog.noParameters")}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {parameters.map((param) => {
        const label = param.label || param.name;
        const value = values[param.name] ?? defaultFor(param);

        if (param.type === "boolean") {
          return (
            <div
              key={param.name}
              className="flex items-center justify-between gap-3"
            >
              <div className="flex flex-col gap-0.5">
                <Label htmlFor={`param-${param.name}`}>{label}</Label>
                {param.description && (
                  <span className="text-xs text-muted-foreground">
                    {param.description}
                  </span>
                )}
              </div>
              <Switch
                id={`param-${param.name}`}
                checked={Boolean(value)}
                onCheckedChange={(checked) => onChange(param.name, checked)}
                disabled={disabled}
              />
            </div>
          );
        }

        if (param.type === "file") {
          const fileValue = value as FileParamValue | File | null;
          const selected =
            fileValue instanceof File
              ? fileValue
              : fileValue && typeof fileValue === "object" && "file" in fileValue
                ? fileValue.file
                : null;
          const staged =
            fileValue && typeof fileValue === "object" && "file_id" in fileValue
              ? (fileValue as FileParamValue)
              : null;
          return (
            <div key={param.name} className="flex flex-col gap-1">
              <Label htmlFor={`param-${param.name}`}>
                {label}
                {param.required && " *"}
              </Label>
              {param.description && (
                <span className="text-xs text-muted-foreground">
                  {param.description}
                </span>
              )}
              <Input
                id={`param-${param.name}`}
                type="file"
                onChange={(e) => {
                  const picked = e.target.files?.[0] ?? null;
                  onChange(param.name, picked ? { file: picked } : null);
                }}
                disabled={disabled}
              />
              {selected && (
                <span className="text-xs text-muted-foreground">
                  {selected.name} ({Math.round(selected.size / 1024)} KB)
                </span>
              )}
              {staged?.filename && !selected && (
                <span className="text-xs text-muted-foreground">
                  {staged.filename}
                </span>
              )}
            </div>
          );
        }

        if (param.type === "json") {
          const text =
            typeof value === "string"
              ? value
              : JSON.stringify(value ?? {}, null, 2);
          return (
            <div key={param.name} className="flex flex-col gap-1">
              <Label htmlFor={`param-${param.name}`}>
                {label}
                {param.required && " *"}
              </Label>
              {param.description && (
                <span className="text-xs text-muted-foreground">
                  {param.description}
                </span>
              )}
              <Textarea
                id={`param-${param.name}`}
                className="font-mono text-xs"
                rows={4}
                value={text}
                onChange={(e) => onChange(param.name, e.target.value)}
                disabled={disabled}
              />
            </div>
          );
        }

        return (
          <div key={param.name} className="flex flex-col gap-1">
            <Label htmlFor={`param-${param.name}`}>
              {label}
              {param.required && " *"}
            </Label>
            {param.description && (
              <span className="text-xs text-muted-foreground">
                {param.description}
              </span>
            )}
            <Input
              id={`param-${param.name}`}
              type={
                param.type === "number"
                  ? "number"
                  : param.type === "secret"
                    ? "password"
                    : "text"
              }
              value={value === undefined || value === null ? "" : String(value)}
              onChange={(e) => {
                const raw = e.target.value;
                if (param.type === "number") {
                  onChange(param.name, raw === "" ? "" : Number(raw));
                } else {
                  onChange(param.name, raw);
                }
              }}
              disabled={disabled}
            />
          </div>
        );
      })}
    </div>
  );
}

export function buildParameterDefaults(
  parameters: WorkflowParameter[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const param of parameters) {
    out[param.name] = defaultFor(param);
  }
  return out;
}

export function parseParameterValues(
  parameters: WorkflowParameter[],
  values: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const param of parameters) {
    const raw = values[param.name];
    if (raw === "" || raw === undefined || raw === null) {
      if (param.required) {
        out[param.name] = raw;
      }
      continue;
    }
    if (param.type === "json") {
      out[param.name] =
        typeof raw === "string" ? JSON.parse(raw) : raw;
    } else if (param.type === "file") {
      if (raw && typeof raw === "object" && "file_id" in (raw as object)) {
        out[param.name] = { file_id: (raw as FileParamValue).file_id };
      } else if (raw && typeof raw === "object" && "file" in (raw as object)) {
        out[param.name] = raw;
      }
    } else if (param.type === "number") {
      out[param.name] = typeof raw === "number" ? raw : Number(raw);
    } else {
      out[param.name] = raw;
    }
  }
  return out;
}
