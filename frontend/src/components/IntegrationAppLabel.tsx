import { getIntegrationAppMeta } from "@/lib/integrationIcons";
import { cn } from "@/lib/utils";

interface Props {
  app: string;
  className?: string;
  showIcon?: boolean;
}

export function IntegrationAppLabel({
  app,
  className,
  showIcon = true,
}: Props) {
  const meta = getIntegrationAppMeta(app);
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      {showIcon && (
        <span className="text-sm leading-none" aria-hidden>
          {meta.icon}
        </span>
      )}
      <span>{meta.label}</span>
    </span>
  );
}
