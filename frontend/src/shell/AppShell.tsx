import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bot,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Download,
  Fingerprint,
  Globe,
  KeyRound,
  ListChecks,
  LogOut,
  Settings as SettingsIcon,
  Shield,
  Users,
  Workflow,
} from "lucide-react";
import { useAuth } from "@/auth/useAuth";
import { ROUTES, routePath } from "@/routes";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const SIDEBAR_COLLAPSED_KEY = "auto-agent.sidebar.collapsed";

interface NavItem {
  to: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { to: routePath.workflows(), labelKey: "nav.workflows", icon: Workflow },
  { to: routePath.tasks(), labelKey: "nav.tasks", icon: Bot },
  { to: routePath.recordings(), labelKey: "nav.recordings", icon: CircleDot },
  { to: routePath.browserSessions(), labelKey: "nav.browserSessions", icon: Globe },
  { to: routePath.browserProfiles(), labelKey: "nav.browserProfiles", icon: Fingerprint },
  { to: routePath.credentials(), labelKey: "nav.credentials", icon: KeyRound },
  { to: routePath.runs(), labelKey: "nav.runs", icon: ListChecks },
  { to: routePath.members(), labelKey: "nav.members", icon: Users },
  { to: routePath.settings(), labelKey: "nav.settings", icon: SettingsIcon },
  { to: routePath.clientDownload(), labelKey: "nav.clientDownload", icon: Download },
];

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppShell() {
  const { t } = useTranslation();
  const { user, logout, bypass } = useAuth();
  const [collapsed, setCollapsed] = useState(readCollapsed);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      // ignore
    }
  }, [collapsed]);

  const navLinkClass = (isActive: boolean) =>
    cn(
      "group flex items-center rounded-md text-sm transition-colors",
      "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
      collapsed ? "justify-center px-2 py-2" : "gap-2.5 px-3 py-2",
      isActive && "bg-accent font-medium text-foreground",
    );

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        <aside
          className={cn(
            "flex shrink-0 flex-col border-r bg-muted/30 transition-[width] duration-200 ease-in-out",
            collapsed ? "w-14" : "w-60",
          )}
        >
          <div
            className={cn(
              "flex items-center pt-5",
              collapsed ? "flex-col gap-2 px-2 pb-2" : "justify-between gap-2 px-4 pb-4",
            )}
          >
            <NavLink
              to={ROUTES.workflows}
              className={cn(
                "flex items-center font-semibold tracking-tight text-foreground hover:text-primary",
                collapsed ? "justify-center" : "min-w-0 flex-1 gap-2 text-[15px]",
              )}
              title={collapsed ? t("nav.brand") : undefined}
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Workflow className="h-3.5 w-3.5" />
              </span>
              {!collapsed && (
                <span className="truncate">{t("nav.brand")}</span>
              )}
            </NavLink>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0 text-muted-foreground"
              onClick={() => setCollapsed((c) => !c)}
              aria-label={
                collapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")
              }
            >
              {collapsed ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronLeft className="h-4 w-4" />
              )}
            </Button>
          </div>
          <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const label = t(item.labelKey);
              const link = (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => navLinkClass(isActive)}
                >
                  <Icon className="h-4 w-4 shrink-0 opacity-80 group-hover:opacity-100" />
                  {!collapsed && <span className="truncate">{label}</span>}
                </NavLink>
              );
              if (!collapsed) return link;
              return (
                <Tooltip key={item.to}>
                  <TooltipTrigger asChild>{link}</TooltipTrigger>
                  <TooltipContent side="right">{label}</TooltipContent>
                </Tooltip>
              );
            })}
            {user?.is_platform_admin && (
              <>
                {(() => {
                  const label = t("nav.platformAdmin");
                  const link = (
                    <NavLink
                      to={routePath.adminSection("orgs")}
                      className={({ isActive }) => navLinkClass(isActive)}
                    >
                      <Shield className="h-4 w-4 shrink-0 opacity-80 group-hover:opacity-100" />
                      {!collapsed && <span className="truncate">{label}</span>}
                    </NavLink>
                  );
                  if (!collapsed) return link;
                  return (
                    <Tooltip>
                      <TooltipTrigger asChild>{link}</TooltipTrigger>
                      <TooltipContent side="right">{label}</TooltipContent>
                    </Tooltip>
                  );
                })()}
              </>
            )}
          </nav>
          <Separator />
          <div className="px-2 py-2">
            {!bypass && user && !collapsed && (
              <div className="mb-2 px-3 text-xs text-muted-foreground">
                <div className="truncate font-medium text-foreground">
                  {user.name || user.email}
                </div>
                <div className="truncate">{user.email}</div>
              </div>
            )}
            {!bypass && (
              collapsed ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => void logout()}
                      className={navLinkClass(false)}
                      aria-label={t("auth.signOut")}
                    >
                      <LogOut className="h-4 w-4 opacity-80" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">{t("auth.signOut")}</TooltipContent>
                </Tooltip>
              ) : (
                <button
                  type="button"
                  onClick={() => void logout()}
                  className={cn(navLinkClass(false), "w-full")}
                >
                  <LogOut className="h-4 w-4 opacity-80" />
                  <span>{t("auth.signOut")}</span>
                </button>
              )
            )}
          </div>
          {!collapsed && (
            <>
              <Separator />
              <div className="px-4 py-3 text-[11px] text-muted-foreground">
                {t("nav.footer")}
              </div>
            </>
          )}
        </aside>
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
          <Outlet />
        </main>
      </div>
    </TooltipProvider>
  );
}
