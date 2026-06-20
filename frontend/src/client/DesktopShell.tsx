import { NavLink, Outlet } from "react-router-dom";
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
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/runs", label: "Run console", icon: Play, end: false },
  { to: "/workflows", label: "Workflows", icon: Workflow, end: false },
  { to: "/recordings", label: "Recordings", icon: Circle, end: false },
  { to: "/tasks/new", label: "Autonomous task", icon: Bot, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
] as const;

export function DesktopShell() {
  const { session, logout } = useDesktopAuth();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/30">
        <div className="px-4 py-5">
          <div className="font-semibold tracking-tight">Auto Agent Client</div>
          <div className="mt-1 truncate text-xs text-muted-foreground">
            {session?.displayName}
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 px-2">
          {NAV.map((item) => {
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
            Sign out
          </Button>
        </div>
      </aside>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
