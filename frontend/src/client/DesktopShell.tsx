import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Circle,
  LayoutDashboard,
  LogOut,
  Play,
  Settings,
  Workflow,
} from "lucide-react";
import { useDesktopAuth } from "./DesktopAuthContext";
import { isDesktopCloudUrlBakedIn, desktopDefaultCloudUrl } from "./cloudUrl";
import { isGenericDisplayName } from "./session";
import { useRuntimeStatus } from "./RuntimeStatusContext";
import { WorkerCloudWarningBanner } from "./WorkerCloudWarningBanner";
import type { DesktopSession } from "./types";
import { isTauriShell } from "./tauriShell";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

function sidebarSubtitle(session: DesktopSession | null | undefined): string {
  if (!session) return "";
  const name = session.displayName?.trim();
  if (name && !isGenericDisplayName(name)) {
    return name;
  }
  try {
    const host = new URL(session.cloudUrl).hostname;
    if (!isGenericDisplayName(host)) {
      return host;
    }
  } catch {
    if (session.cloudUrl && !isGenericDisplayName(session.cloudUrl)) {
      return session.cloudUrl;
    }
  }
  if (isDesktopCloudUrlBakedIn()) {
    try {
      return new URL(desktopDefaultCloudUrl()).hostname;
    } catch {
      return desktopDefaultCloudUrl();
    }
  }
  return "";
}

export function DesktopShell() {
  const { t } = useTranslation();
  const { session, logout } = useDesktopAuth();
  const { runtimeReady } = useRuntimeStatus();

  const navPrimary = [
    { to: "/", label: t("desktop.nav.home"), icon: LayoutDashboard, end: true },
    { to: "/workflows", label: t("nav.workflows"), icon: Workflow, end: false },
    { to: "/runs", label: t("desktop.nav.runs"), icon: Play, end: false },
    { to: "/settings", label: t("nav.settings"), icon: Settings, end: false },
  ] as const;

  const navAdvanced = [
    { to: "/recordings", label: t("nav.recordings"), icon: Circle, end: false },
    {
      to: "/tasks/new",
      label: t("desktop.nav.autonomousTask"),
      icon: Bot,
      end: false,
    },
  ] as const;

  const subtitle = sidebarSubtitle(session) || t("desktop.signedIn");

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/30">
        <div
          className={cn(
            "px-4 pb-5",
            isTauriShell() ? "pt-[52px]" : "pt-5",
          )}
          data-tauri-drag-region
        >
          <div className="font-semibold tracking-tight">{t("nav.brand")}</div>
          <div className="mt-1 flex items-center gap-1.5 truncate text-xs text-muted-foreground">
            <Circle
              className={cn(
                "h-2 w-2 shrink-0 fill-current",
                runtimeReady ? "text-emerald-500" : "text-amber-500",
              )}
              aria-hidden
            />
            <span className="truncate">{subtitle}</span>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 px-2">
          {navPrimary.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground",
                    isActive && "bg-accent font-medium text-foreground",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            );
          })}
          <div className="px-3 pb-1 pt-4 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
            {t("desktop.nav.cloudSection")}
          </div>
          {navAdvanced.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground",
                    isActive && "bg-accent font-medium text-foreground",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <Separator />
        <div className="p-2">
          <Button
            variant="ghost"
            className="w-full justify-start gap-2"
            onClick={() => logout()}
          >
            <LogOut className="h-4 w-4" />
            {t("desktop.signOut")}
          </Button>
        </div>
      </aside>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <WorkerCloudWarningBanner />
        <Outlet />
      </main>
    </div>
  );
}
