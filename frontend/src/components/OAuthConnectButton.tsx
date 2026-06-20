import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getIntegrationAppMeta } from "@/lib/integrationIcons";

interface Props {
  connectApp: string;
  credentialId: string;
  disabled?: boolean;
}

export function oauthConnectUrl(connectApp: string, credentialId: string): string {
  const params = new URLSearchParams({ credential_id: credentialId });
  return `/api/oauth2/${encodeURIComponent(connectApp)}/connect?${params}`;
}

export function OAuthConnectButton({
  connectApp,
  credentialId,
  disabled,
}: Props) {
  const { t } = useTranslation();
  const meta = getIntegrationAppMeta(connectApp);

  function handleConnect() {
    window.location.href = oauthConnectUrl(connectApp, credentialId);
  }

  return (
    <Button
      type="button"
      variant="secondary"
      onClick={handleConnect}
      disabled={disabled || !credentialId}
      className="w-full"
    >
      <ExternalLink className="mr-2 h-4 w-4" />
      {t("pages.credentials.connectOAuth", { app: meta.label })}
    </Button>
  );
}
