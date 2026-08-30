import { Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiClient } from "@/api-platform";
import type { RouteSkillBucketOut, RouteSkillOut } from "@/types-platform";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const QK_ROUTE_SKILLS = ["route-skills", "list"] as const;
const QK_BUCKETS = ["route-skills", "buckets"] as const;

export function SettingsRouteSkillsTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [view, setView] = useState<"list" | "buckets">("buckets");

  const listQuery = useQuery({
    queryKey: QK_ROUTE_SKILLS,
    queryFn: () => apiClient.routeSkills.list(),
  });

  const bucketsQuery = useQuery({
    queryKey: QK_BUCKETS,
    queryFn: () => apiClient.routeSkills.buckets(),
  });

  const updateMut = useMutation({
    mutationFn: ({
      skillId,
      enabled,
    }: {
      skillId: string;
      enabled: boolean;
    }) => apiClient.routeSkills.update(skillId, { enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QK_ROUTE_SKILLS });
      void queryClient.invalidateQueries({ queryKey: QK_BUCKETS });
    },
  });

  const skills = listQuery.data ?? [];
  const buckets = bucketsQuery.data ?? [];

  const bucketsByDomain = buckets.reduce<Record<string, RouteSkillBucketOut[]>>(
    (acc, row) => {
      const key = row.domain || "unknown";
      acc[key] = acc[key] ?? [];
      acc[key].push(row);
      return acc;
    },
    {},
  );

  return (
    <Card className="border-0 bg-card shadow-sm">
      <CardHeader>
        <CardTitle className="text-base">
          {t("pages.settings.routeSkillsTitle")}
        </CardTitle>
        <CardDescription>
          {t("pages.settings.routeSkillsDescription")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs
          value={view}
          onValueChange={(v) => setView(v as "list" | "buckets")}
        >
          <TabsList className="mb-4">
            <TabsTrigger value="buckets">
              {t("pages.settings.routeSkillsViewBuckets")}
            </TabsTrigger>
            <TabsTrigger value="list">
              {t("pages.settings.routeSkillsViewList")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="buckets">
            {bucketsQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">
                {t("common.loading")}
              </p>
            ) : buckets.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {t("pages.settings.routeSkillsEmpty")}
              </p>
            ) : (
              <div className="space-y-6">
                {Object.entries(bucketsByDomain).map(([domain, rows]) => (
                  <div key={domain}>
                    <h3 className="mb-2 text-sm font-medium">{domain}</h3>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>
                            {t("pages.settings.routeSkillsCapability")}
                          </TableHead>
                          <TableHead>
                            {t("pages.settings.routeSkillsUrl")}
                          </TableHead>
                          <TableHead>
                            {t("pages.settings.routeSkillsPending")}
                          </TableHead>
                          <TableHead>
                            {t("pages.settings.routeSkillsEnabled")}
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {rows.map((row) => (
                          <TableRow key={row.url_pattern}>
                            <TableCell>{row.capability}</TableCell>
                            <TableCell className="max-w-xs truncate font-mono text-xs">
                              {row.url_pattern}
                            </TableCell>
                            <TableCell>
                              {row.pending_proposals > 0 ? (
                                <Badge variant="secondary">
                                  {row.pending_proposals}
                                </Badge>
                              ) : (
                                "—"
                              )}
                            </TableCell>
                            <TableCell>
                              {row.route_skill_id ? (
                                <Switch
                                  checked={row.enabled}
                                  onCheckedChange={(checked) =>
                                    updateMut.mutate({
                                      skillId: row.route_skill_id!,
                                      enabled: checked,
                                    })
                                  }
                                  disabled={updateMut.isPending}
                                />
                              ) : (
                                <span className="text-xs text-muted-foreground">
                                  {t("pages.settings.routeSkillsNotAdopted")}
                                </span>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="list">
            {listQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">
                {t("common.loading")}
              </p>
            ) : skills.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {t("pages.settings.routeSkillsEmpty")}
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("pages.settings.routeSkillsUrl")}</TableHead>
                    <TableHead>{t("pages.settings.routeSkillsScope")}</TableHead>
                    <TableHead>
                      {t("pages.settings.routeSkillsEnabled")}
                    </TableHead>
                    <TableHead className="text-right">
                      {t("pages.settings.routeSkillsActions")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {skills.map((skill: RouteSkillOut) => (
                    <Fragment key={skill.id}>
                      <TableRow>
                        <TableCell className="max-w-xs truncate font-mono text-xs">
                          {skill.url_pattern}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{skill.scope}</Badge>
                        </TableCell>
                        <TableCell>
                          <Switch
                            checked={skill.enabled}
                            onCheckedChange={(checked) =>
                              updateMut.mutate({
                                skillId: skill.id,
                                enabled: checked,
                              })
                            }
                            disabled={updateMut.isPending}
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              setExpandedId(
                                expandedId === skill.id ? null : skill.id,
                              )
                            }
                          >
                            {expandedId === skill.id
                              ? t("recordings.proposalsHide")
                              : t("recordings.proposalsPreview")}
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expandedId === skill.id && (
                        <TableRow>
                          <TableCell colSpan={4}>
                            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-muted/40 p-3 text-xs">
                              {skill.prompt}
                            </pre>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  ))}
                </TableBody>
              </Table>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
