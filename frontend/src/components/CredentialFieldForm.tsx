import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CredentialTypeFieldSpec } from "@/types-platform";

export interface CredentialFieldValue {
  value: string;
  maskedFromServer: string | null;
}

interface Props {
  fields: CredentialTypeFieldSpec[];
  values: Record<string, CredentialFieldValue>;
  onChange(fieldName: string, patch: Partial<CredentialFieldValue>): void;
  credentialName: string;
  editing: boolean;
}

export function CredentialFieldForm({
  fields,
  values,
  onChange,
  credentialName,
  editing,
}: Props) {
  const { t } = useTranslation();

  if (fields.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {t("pages.credentials.noSchemaFields")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {fields.map((field) => {
        const row = values[field.name] ?? {
          value: "",
          maskedFromServer: null,
        };
        const isSecret = field.kind === "secret";
        const placeholder =
          editing && row.maskedFromServer
            ? t("pages.credentials.keepValue", {
                masked: row.maskedFromServer,
              })
            : undefined;

        return (
          <div key={field.name} className="grid gap-1.5">
            <Label htmlFor={`cred-field-${field.name}`}>
              {field.label || field.name}
              {field.required ? " *" : ""}
            </Label>
            <Input
              id={`cred-field-${field.name}`}
              type={isSecret ? "password" : field.kind === "number" ? "number" : "text"}
              value={row.value}
              placeholder={placeholder}
              onChange={(e) =>
                onChange(field.name, { value: e.target.value })
              }
            />
            {credentialName.trim() && (
              <p className="font-mono text-[11px] text-muted-foreground">
                {`{{cred.${credentialName.trim()}.${field.name}}}`}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
