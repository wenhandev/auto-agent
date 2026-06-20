import { Building2, Globe, KeyRound, Shield, Users } from "lucide-react";
import { Navigate, NavLink, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/useAuth";
import { routePath } from "@/routes";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { AdminOrgsPage } from "./AdminOrgsPage";
import { AdminUsersPage } from "./AdminUsersPage";
import { AdminDomainsPage } from "./AdminDomainsPage";
import { AdminAuthenticationPage } from "./AdminAuthenticationPage";

export type AdminSection = "orgs" | "users" | "domains" | "authentication";

const SECTIONS: AdminSection[] = ["orgs", "users", "domains", "authentication"];

const NAV: {
  section: AdminSection;
  labelKey: string;
  icon: typeof Building2;
}[] = [
  { section: "orgs", labelKey: "admin.navOrgs", icon: Building2 },
  { section: "users", labelKey: "admin.navUsers", icon: Users },
  { section: "domains", labelKey: "admin.navDomains", icon: Globe },
  { section: "authentication", labelKey: "admin.navAuthentication", icon: KeyRound },
];

function sectionTitleKey(section: AdminSection): string {
  return `admin.${section}.title`;
}

export function AdminConsolePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { section: rawSection } = useParams<{ section: string }>();

  if (!user?.is_platform_admin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="max-w-md rounded-lg border border-destructive/50 bg-destructive/10 p-6">
          <div className="mb-2 flex items-center gap-2 font-semibold text-destructive">
            <Shield className="size-4" aria-hidden />
            {t("admin.accessDenied.title")}
          </div>
          <p className="text-sm text-muted-foreground">
            {t("admin.accessDenied.description")}
          </p>
        </div>
      </div>
    );
  }

  const section = (rawSection ?? "orgs") as AdminSection;
  if (!SECTIONS.includes(section)) {
    return <Navigate to={routePath.adminSection("orgs")} replace />;
  }

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-muted/25">
        <div className="border-b border-border px-4 py-5">
          <p className="text-sm font-semibold tracking-tight">{t("admin.title")}</p>
          <p className="text-xs text-muted-foreground">{user.email}</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3" aria-label={t("admin.title")}>
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <Button
                key={item.section}
                type="button"
                variant="ghost"
                className={cn(
                  "justify-start gap-2",
                  section === item.section && "bg-accent text-accent-foreground",
                )}
                asChild
              >
                <NavLink to={routePath.adminSection(item.section)}>
                  <Icon className="size-4 opacity-80" aria-hidden />
                  {t(item.labelKey)}
                </NavLink>
              </Button>
            );
          })}
        </nav>
        <div className="border-t border-border p-3">
          <Button type="button" variant="outline" className="w-full" asChild>
            <NavLink to={routePath.workflows()}>{t("admin.backToApp")}</NavLink>
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight">
            {t(sectionTitleKey(section))}
          </h1>
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          {section === "orgs" && <AdminOrgsPage />}
          {section === "users" && <AdminUsersPage />}
          {section === "domains" && <AdminDomainsPage />}
          {section === "authentication" && <AdminAuthenticationPage />}
        </main>
      </div>
    </div>
  );
}
