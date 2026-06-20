import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import { apiClient } from "@/api-platform";
import { useAuth } from "@/auth/useAuth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const QK = ["admin", "users"] as const;

export function AdminUsersPage() {
  const { t } = useTranslation();
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: QK,
    queryFn: () => apiClient.admin.listUsers(),
  });

  const updateMut = useMutation({
    mutationFn: ({
      userId,
      is_platform_admin,
      disabled,
    }: {
      userId: string;
      is_platform_admin?: boolean;
      disabled?: boolean;
    }) => apiClient.admin.updateUser(userId, { is_platform_admin, disabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: QK }),
  });

  const deleteMut = useMutation({
    mutationFn: (userId: string) => apiClient.admin.deleteUser(userId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: QK }),
  });

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle>{t("admin.users.title")}</CardTitle>
        <CardDescription>{t("admin.users.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {query.data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("admin.users.colEmail")}</TableHead>
                <TableHead>{t("admin.users.colOrgs")}</TableHead>
                <TableHead>{t("admin.users.colPlatformAdmin")}</TableHead>
                <TableHead>{t("admin.users.colDisabled")}</TableHead>
                <TableHead className="text-right">{t("admin.users.colActions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>
                    <div className="font-medium">{u.email}</div>
                    {u.name && (
                      <div className="text-xs text-muted-foreground">{u.name}</div>
                    )}
                  </TableCell>
                  <TableCell className="text-xs">
                    {u.memberships.map((m) => (
                      <Badge key={m.org_id} variant="secondary" className="mr-1">
                        {m.org_name} ({m.role})
                      </Badge>
                    ))}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={u.is_platform_admin}
                      disabled={updateMut.isPending || u.id === currentUser?.id}
                      onCheckedChange={(checked) =>
                        updateMut.mutate({
                          userId: u.id,
                          is_platform_admin: checked,
                        })
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={!!u.disabled_at}
                      disabled={updateMut.isPending || u.id === currentUser?.id}
                      onCheckedChange={(checked) =>
                        updateMut.mutate({ userId: u.id, disabled: checked })
                      }
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={deleteMut.isPending || u.id === currentUser?.id}
                      onClick={() => {
                        if (
                          window.confirm(
                            t("admin.users.deleteConfirm", { email: u.email }),
                          )
                        ) {
                          deleteMut.mutate(u.id);
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
      </CardContent>
    </Card>
  );
}
