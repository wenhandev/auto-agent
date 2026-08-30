import i18n from "@/i18n";

/** User-facing labels for runtime preflight checks (hide internal IDs). */

export function friendlyCheckLabel(id: string): string {
  const key = `desktop.checks.${id}`;
  const translated = i18n.t(key);
  return translated !== key ? translated : id.replace(/_/g, " ");
}

export function friendlyEnvStatus(status: string): string {
  const key = `desktop.envStatus.${status}`;
  const translated = i18n.t(key);
  if (translated !== key) return translated;
  return i18n.t("desktop.envStatus.unknown");
}
