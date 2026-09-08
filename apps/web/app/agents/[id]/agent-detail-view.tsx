"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingBlock } from "@/components/states";
import { ExecutionStatusBadge, PermissionBadge, RiskBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAgent } from "@/hooks/use-safeops";

export function AgentDetailView({ agentId }: { agentId: string }) {
  const { data: agent, isLoading, error } = useAgent(agentId);

  return (
    <div>
      <Button variant="ghost" size="sm" className="mb-2" render={<Link href="/agents" />}>
        <ArrowLeft className="size-3.5" />
        Agents
      </Button>

      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={5} />}

      {agent && (
        <>
          <PageHeader
            title={agent.name}
            description={agent.description ?? undefined}
            actions={
              <>
                <RiskBadge level={agent.risk_level} />
              </>
            }
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Tool permissions</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tool</TableHead>
                      <TableHead>Permission</TableHead>
                      <TableHead>Risk category</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {agent.permissions.map((permission) => (
                      <TableRow key={permission.tool_id}>
                        <TableCell className="font-mono text-xs">
                          {permission.tool_name}
                        </TableCell>
                        <TableCell>
                          <PermissionBadge permission={permission.permission} />
                        </TableCell>
                        <TableCell>
                          <RiskBadge level={permission.risk_category} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Recent executions</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-1">
                {agent.recent_executions.length === 0 && (
                  <p className="text-sm text-muted-foreground">No executions yet.</p>
                )}
                {agent.recent_executions.map((execution) => (
                  <Link
                    key={execution.id}
                    href={`/executions/${execution.id}`}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  >
                    <span className="truncate">{execution.objective}</span>
                    <ExecutionStatusBadge status={execution.status} />
                  </Link>
                ))}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
