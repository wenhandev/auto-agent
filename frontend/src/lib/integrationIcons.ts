export interface IntegrationAppMeta {
  label: string;
  icon: string;
}

const APP_META: Record<string, IntegrationAppMeta> = {
  slack: { label: "Slack", icon: "💬" },
  gmail: { label: "Gmail", icon: "📧" },
  google_sheets: { label: "Google Sheets", icon: "📊" },
  notion: { label: "Notion", icon: "📝" },
  _fixture: { label: "Fixture", icon: "🧪" },
};

export function getIntegrationAppMeta(app: string): IntegrationAppMeta {
  return (
    APP_META[app] ?? {
      label: app.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      icon: "🔌",
    }
  );
}
