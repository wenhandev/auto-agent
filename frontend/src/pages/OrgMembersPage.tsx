import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Pencil, Trash2, UserPlus } from "lucide-react";
import { useAuth } from "@/auth/useAuth";
import { apiClient, ApiError } from "@/api-platform";
import type { OrgMemberOut } from "@/types-platform";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

const ROLES = ["admin", "member", "viewer"] as const;

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function formatError(err: unknown): string {
  return err instanceof ApiError
    ? `${err.status}: ${typeof err.body === "string" ? err.body : JSON.stringify(err.body)}`
    : err instanceof Error
      ? err.message
      : String(err);
}

function canManageMembers(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin";
}

interface InviteModalProps {
  open: boolean;
  onClose(): void;
  orgId: string;
}

function InviteModal({ open, onClose, orgId }: InviteModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<string>("member");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setEmail("");
      setName("");
      setPassword("");
      setRole("member");
      setError(null);
    }
  }, [open]);

  const inviteMut = useMutation({
    mutationFn: () =>
      apiClient.orgs.inviteMember(orgId, {
        email: email.trim(),
        name: name.trim() || null,
        password: password.trim() || null,
        role,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["org-members", orgId] });
      onClose();
    },
    onError: (err: unknown) => setError(formatError(err)),
  });

  function onSubmit() {
    if (!email.trim()) {
      setError(t("pages.members.emailRequired"));
      return;
    }
    inviteMut.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("pages.members.inviteTitle")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>{t("pages.members.emailLabel")}</Label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("pages.members.emailPlaceholder")}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t("pages.members.nameLabel")}</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("pages.members.namePlaceholder")}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t("pages.members.passwordLabel")}</Label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("pages.members.passwordPlaceholder")}
            />
            <p className="text-xs text-muted-foreground">
              {t("pages.members.passwordHint")}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t("pages.members.roleLabel")}</Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(`pages.members.roles.${r}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={onSubmit} disabled={inviteMut.isPending}>
            {inviteMut.isPending
              ? t("pages.members.inviting")
              : t("pages.members.inviteCta")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface EditRoleModalProps {
  open: boolean;
  member: OrgMemberOut | null;
  onClose(): void;
  orgId: string;
}

function EditRoleModal({ open, member, onClose, orgId }: EditRoleModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [role, setRole] = useState("member");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && member) {
      setRole(member.role);
      setError(null);
    }
  }, [open, member]);

  const updateMut = useMutation({
    mutationFn: () =>
      apiClient.orgs.updateMemberRole(orgId, member!.user_id, { role }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["org-members", orgId] });
      onClose();
    },
    onError: (err: unknown) => setError(formatError(err)),
  });

  if (!member) return null;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("pages.members.editRoleTitle")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">{member.email}</p>
          <div className="flex flex-col gap-1.5">
            <Label>{t("pages.members.roleLabel")}</Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(`pages.members.roles.${r}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
            {updateMut.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function OrgMembersPage() {
  const { t } = useTranslation();
  const { user, bypass } = useAuth();
  const queryClient = useQueryClient();
  const orgId = user?.current_org_id ?? "";
  const canManage = bypass || canManageMembers(user?.role);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [editing, setEditing] = useState<OrgMemberOut | null>(null);

  const membersQuery = useQuery({
    queryKey: ["org-members", orgId],
    queryFn: () => apiClient.orgs.listMembers(orgId),
    enabled: !!orgId,
  });

  const removeMut = useMutation({
    mutationFn: (userId: string) => apiClient.orgs.removeMember(orgId, userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["org-members", orgId] });
    },
  });

  const members = membersQuery.data ?? [];

  function onRemove(member: OrgMemberOut) {
    if (
      !window.confirm(
        t("pages.members.confirmRemove", { email: member.email }),
      )
    ) {
      return;
    }
    removeMut.mutate(member.user_id);
  }

  if (!orgId && !bypass) {
    return (
      <div className="flex h-full flex-col overflow-auto p-6">
        <p className="text-sm text-muted-foreground">
          {t("pages.members.noOrg")}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="flex items-center justify-between border-b bg-card/40 px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold">{t("pages.members.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("pages.members.subtitle")}
          </p>
        </div>
        {canManage && (
          <Button size="sm" onClick={() => setInviteOpen(true)}>
            <UserPlus className="mr-1.5 h-3.5 w-3.5" />
            {t("pages.members.inviteButton")}
          </Button>
        )}
      </div>

      <div className="p-6">
        {membersQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : membersQuery.error ? (
          <p className="text-sm text-destructive">
            {formatError(membersQuery.error)}
          </p>
        ) : members.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("pages.members.empty")}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("pages.members.table.email")}</TableHead>
                <TableHead>{t("pages.members.table.name")}</TableHead>
                <TableHead>{t("pages.members.table.role")}</TableHead>
                <TableHead>{t("pages.members.table.joined")}</TableHead>
                {canManage && (
                  <TableHead className="text-right">
                    {t("pages.members.table.actions")}
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => (
                <TableRow key={member.user_id}>
                  <TableCell>{member.email}</TableCell>
                  <TableCell>{member.name || t("common.dash")}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {t(`pages.members.roles.${member.role}`, member.role)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTime(member.created_at)}
                  </TableCell>
                  {canManage && (
                    <TableCell className="text-right">
                      {member.role === "owner" ? (
                        <span className="text-xs text-muted-foreground">—</span>
                      ) : (
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setEditing(member)}
                          >
                            <Pencil className="mr-1 h-3.5 w-3.5" />
                            {t("pages.members.changeRole")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onRemove(member)}
                            disabled={removeMut.isPending}
                          >
                            <Trash2 className="mr-1 h-3.5 w-3.5" />
                            {t("common.remove")}
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {orgId && (
        <>
          <InviteModal
            open={inviteOpen}
            onClose={() => setInviteOpen(false)}
            orgId={orgId}
          />
          <EditRoleModal
            open={!!editing}
            member={editing}
            onClose={() => setEditing(null)}
            orgId={orgId}
          />
        </>
      )}
    </div>
  );
}
