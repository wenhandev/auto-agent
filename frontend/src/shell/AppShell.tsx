import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  KeyRound,
  ListChecks,
  Settings as SettingsIcon,
  Workflow,
} from "lucide-react";
import { ROUTES, routePath } from "@/routes";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";

interface NavItem {
  to: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { to: routePath.workflows(), labelKey: "nav.workflows", icon: Workflow },
  { to: routePath.credentials(), labelKey: "nav.credentials", icon: KeyRound },
  { to: routePath.runs(), labelKey: "nav.runs", icon: ListChecks },
  { to: routePath.settings(), labelKey: "nav.settings", icon: SettingsIcon },
];

export function AppShell() {
  const { t } = useTranslation();
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-card/40">
        <NavLink
          to={ROUTES.workflows}
          className="px-5 pb-4 pt-5 text-base font-semibold tracking-wide text-foreground hover:text-primary"
        >
          {t("nav.brand")}
        </NavLink>
        <Separator />
        <nav className="flex flex-1 flex-col gap-1 p-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    isActive &&
                      "bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                <span>{t(item.labelKey)}</span>
              </NavLink>
            );
          })}
        </nav>
        <Separator />
        <div className="px-5 py-3 text-[11px] text-muted-foreground">
          {t("nav.footer")}
        </div>
      </aside>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
