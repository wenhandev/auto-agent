import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import { apiClient } from "@/api-platform";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const QK_RULES = ["admin", "domain-rules"] as const;
const QK_ORGS = ["admin", "orgs"] as const;
const ROLES = ["admin", "member", "viewer"] as const;

export function AdminDomainsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [domain, setDomain] = useState("");
  const [orgId, setOrgId] = useState("");
  const [defaultRole, setDefaultRole] = useState<string>("member");

  const orgsQuery = useQuery({
    queryKey: QK_ORGS,
    queryFn: () => apiClient.admin.listOrgs(),
  });

  const rulesQuery = useQuery({
    queryKey: QK_RULES,
    queryFn: () => apiClient.admin.listDomainRules(),
  });

  const createMut = useMutation({
    mutationFn: () =>
      apiClient.admin.createDomainRule({
        domain: domain.trim().toLowerCase(),
        org_id: orgId,
        default_role: defaultRole,
      }),
    onSuccess: () => {
      setDomain("");
      void queryClient.invalidateQueries({ queryKey: QK_RULES });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (ruleId: string) => apiClient.admin.deleteDomainRule(ruleId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: QK_RULES }),
  });

  const orgNameById = new Map(
    (orgsQuery.data ?? []).map((org) => [org.id, org.name]),
  );

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle>{t("admin.domains.title")}</CardTitle>
        <CardDescription>{t("admin.domains.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {rulesQuery.data && rulesQuery.data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("admin.domains.colDomain")}</TableHead>
                <TableHead>{t("admin.domains.colOrg")}</TableHead>
                <TableHead>{t("admin.domains.colRole")}</TableHead>
                <TableHead>{t("admin.domains.colCreated")}</TableHead>
                <TableHead className="text-right">{t("admin.domains.colActions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rulesQuery.data.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell className="font-medium">{rule.domain}</TableCell>
                  <TableCell>
                    {orgNameById.get(rule.org_id) ?? rule.org_id}
                  </TableCell>
                  <TableCell>{rule.default_role}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(rule.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={deleteMut.isPending}
                      onClick={() => {
                        if (window.confirm(t("admin.domains.deleteConfirm"))) {
                          deleteMut.mutate(rule.id);
                        }
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <div className="grid max-w-xl gap-3 sm:grid-cols-2">
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="domain-rule-domain">{t("admin.domains.domainLabel")}</Label>
            <Input
              id="domain-rule-domain"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="example.com"
            />
          </div>
          <div className="grid gap-2">
            <Label>{t("admin.domains.orgLabel")}</Label>
            <Select value={orgId} onValueChange={setOrgId}>
              <SelectTrigger>
                <SelectValue placeholder={t("admin.domains.orgPlaceholder")} />
              </SelectTrigger>
              <SelectContent>
                {(orgsQuery.data ?? []).map((org) => (
                  <SelectItem key={org.id} value={org.id}>
                    {org.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>{t("admin.domains.roleLabel")}</Label>
            <Select value={defaultRole} onValueChange={setDefaultRole}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((role) => (
                  <SelectItem key={role} value={role}>
                    {role}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="sm:col-span-2">
            <Button
              onClick={() => createMut.mutate()}
              disabled={!domain.trim() || !orgId || createMut.isPending}
            >
              {t("admin.domains.create")}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
