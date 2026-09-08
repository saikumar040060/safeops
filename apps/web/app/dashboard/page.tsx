"use client";

import Link from "next/link";
import { Activity, Ban, CheckCircle2, ClipboardList, ShieldAlert } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { ExecutionStatusBadge, ApprovalStatusBadge, IncidentStatusBadge } from "@/components/badges";
import { DemoPanel } from "@/components/demo/demo-panel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDashboardSummary } from "@/hooks/use-safeops";

const SEVERITY_COLORS: Record<string, string> = {
  LOW: "#10b981",
  MEDIUM: "#f59e0b",
  HIGH: "#f97316",
  CRITICAL: "#ef4444",
};

export default function DashboardPage() {
  const { data, isLoading, error } = useDashboardSummary();

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Deploy agents without giving them unchecked power."
      />

      {error && <ErrorState error={error} />}

      {isLoading && <LoadingBlock rows={6} />}

      {data && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard
              label="Active executions"
              value={data.metrics.active_executions}
              icon={Activity}
            />
            <StatCard
              label="Waiting approvals"
              value={data.metrics.waiting_approvals}
              icon={ClipboardList}
              tone="warning"
            />
            <StatCard
              label="Blocked actions"
              value={data.metrics.blocked_actions}
              icon={Ban}
              tone="danger"
            />
            <StatCard
              label="Open incidents"
              value={data.metrics.open_security_incidents}
              icon={ShieldAlert}
              tone="danger"
            />
            <StatCard
              label="Completed"
              value={data.metrics.completed_executions}
              icon={CheckCircle2}
              tone="success"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardHeader>
                <CardTitle className="text-base">Risk assessments by severity</CardTitle>
              </CardHeader>
              <CardContent>
                {data.metrics.risk_assessments_by_severity.length === 0 ? (
                  <EmptyState title="No risk assessments yet" />
                ) : (
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data.metrics.risk_assessments_by_severity}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="severity" fontSize={12} tickLine={false} />
                        <YAxis allowDecimals={false} fontSize={12} tickLine={false} width={24} />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                          {data.metrics.risk_assessments_by_severity.map((entry) => (
                            <Cell
                              key={entry.severity}
                              fill={SEVERITY_COLORS[entry.severity] ?? "#94a3b8"}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="lg:col-span-2">
              <DemoPanel />
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
            <RecentCard title="Recent executions">
              {data.recent_executions.length === 0 ? (
                <EmptyState title="No executions yet" />
              ) : (
                data.recent_executions.map((execution) => (
                  <Link
                    key={execution.id}
                    href={`/executions/${execution.id}`}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  >
                    <span className="truncate">{execution.objective}</span>
                    <ExecutionStatusBadge status={execution.status} />
                  </Link>
                ))
              )}
            </RecentCard>

            <RecentCard title="Recent approvals">
              {data.recent_approvals.length === 0 ? (
                <EmptyState title="No approvals yet" />
              ) : (
                data.recent_approvals.map((approval) => (
                  <Link
                    key={approval.id}
                    href="/approvals"
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  >
                    <span className="truncate">{approval.tool_name}</span>
                    <ApprovalStatusBadge status={approval.status} />
                  </Link>
                ))
              )}
            </RecentCard>

            <RecentCard title="Recent incidents">
              {data.recent_incidents.length === 0 ? (
                <EmptyState title="No incidents" description="Nothing malicious detected yet." />
              ) : (
                data.recent_incidents.map((incident) => (
                  <Link
                    key={incident.id}
                    href={`/security/${incident.id}`}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  >
                    <span className="truncate">{incident.incident_type}</span>
                    <IncidentStatusBadge status={incident.status} />
                  </Link>
                ))
              )}
            </RecentCard>

            <RecentCard title="Recent blocked actions">
              {data.recent_blocked.length === 0 ? (
                <EmptyState title="Nothing blocked" />
              ) : (
                data.recent_blocked.map((event) => (
                  <div
                    key={event.id}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm"
                  >
                    <span className="truncate text-muted-foreground">{event.event_type}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{event.actor}</span>
                  </div>
                ))
              )}
            </RecentCard>
          </div>
        </div>
      )}
    </div>
  );
}

function RecentCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-0.5">{children}</CardContent>
    </Card>
  );
}
