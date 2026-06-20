import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiClient } from "@/api-platform";
import type { AdminOrgOut, DesktopClientPolicy } from "@/types-platform";
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

const QK = ["admin", "orgs"] as const;

const POLICIES: DesktopClientPolicy[] = [
  "approval_required",
  "open",
  "disabled",
];

export function AdminOrgsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const query = useQuery({
    queryKey: QK,
    queryFn: () => apiClient.admin.listOrgs(),
  });

  const createMut = useMutation({
    mutationFn: () => apiClient.admin.createOrg({ name: name.trim() }),
    onSuccess: () => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: QK });
    },
  });

  const updateMut = useMutation({
    mutationFn: ({
      orgId,
      desktop_client_policy,
    }: {
      orgId: string;
      desktop_client_policy: DesktopClientPolicy;
    }) => apiClient.admin.updateOrg(orgId, { desktop_client_policy }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: QK }),
  });

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle>{t("admin.orgs.title")}</CardTitle>
        <CardDescription>{t("admin.orgs.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {query.data && query.data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("admin.orgs.colName")}</TableHead>
                <TableHead>{t("admin.orgs.colPolicy")}</TableHead>
                <TableHead>{t("admin.orgs.colCreated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.map((org: AdminOrgOut) => (
                <TableRow key={org.id}>
                  <TableCell className="font-medium">{org.name}</TableCell>
                  <TableCell>
                    <Select
                      value={org.desktop_client_policy}
                      onValueChange={(v) =>
                        updateMut.mutate({
                          orgId: org.id,
                          desktop_client_policy: v as DesktopClientPolicy,
                        })
                      }
                      disabled={updateMut.isPending}
                    >
                      <SelectTrigger className="w-44">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {POLICIES.map((p) => (
                          <SelectItem key={p} value={p}>
                            {p}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(org.created_at).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <div className="flex max-w-md items-end gap-2">
          <div className="grid flex-1 gap-2">
            <Label htmlFor="org-name">{t("admin.orgs.newName")}</Label>
            <Input
              id="org-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <Button
            onClick={() => createMut.mutate()}
            disabled={!name.trim() || createMut.isPending}
          >
            {t("admin.orgs.create")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
