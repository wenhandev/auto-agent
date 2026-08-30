import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export function DesktopRunsLayout() {
  const { t } = useTranslation();
  const location = useLocation();
  const showTabs =
    location.pathname === "/runs" || location.pathname === "/runs/console";

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
      isActive
        ? "bg-muted text-foreground"
        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
    );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {showTabs && (
        <div className="flex shrink-0 gap-1 border-b px-6 pt-4">
          <NavLink to="/runs" end className={tabClass}>
            {t("desktop.runs.tabHistory")}
          </NavLink>
          <NavLink to="/runs/console" className={tabClass}>
            {t("desktop.runs.tabConsole")}
          </NavLink>
        </div>
      )}
      <Outlet />
    </div>
  );
}
