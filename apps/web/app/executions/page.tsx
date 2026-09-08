"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatDistanceToNow } from "date-fns";

import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { ExecutionStatusBadge, RiskBadge } from "@/components/badges";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useExecutions } from "@/hooks/use-safeops";
import type { ExecutionStatus } from "@/lib/types";

const FILTERS: Array<{ label: string; value: ExecutionStatus | "ALL" }> = [
  { label: "All", value: "ALL" },
  { label: "Running", value: "RUNNING" },
  { label: "Waiting approval", value: "WAITING_APPROVAL" },
  { label: "Blocked", value: "BLOCKED" },
  { label: "Completed", value: "COMPLETED" },
  { label: "Failed", value: "FAILED" },
  { label: "Cancelled", value: "CANCELLED" },
];

export default function ExecutionsPage() {
  const router = useRouter();
  const [status, setStatus] = useState<ExecutionStatus | "ALL">("ALL");
  const { data, isLoading, error } = useExecutions(status === "ALL" ? {} : { status });

  return (
    <div>
      <PageHeader title="Executions" description="Every agent run, past and present." />

      <Tabs value={status} onValueChange={(v) => setStatus(v as ExecutionStatus | "ALL")}>
        <TabsList className="mb-4 flex-wrap">
          {FILTERS.map((filter) => (
            <TabsTrigger key={filter.value} value={filter.value}>
              {filter.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={6} />}

      {data && data.length === 0 && (
        <EmptyState
          title="No executions"
          description="Launch a demo from the dashboard to see one here."
        />
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Objective</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Current step</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((execution) => (
                <TableRow
                  key={execution.id}
                  role="link"
                  tabIndex={0}
                  className="cursor-pointer focus-visible:bg-muted focus-visible:outline-none"
                  onClick={() => router.push(`/executions/${execution.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      router.push(`/executions/${execution.id}`);
                    }
                  }}
                >
                  <TableCell className="max-w-xs truncate font-medium">
                    {execution.objective}
                  </TableCell>
                  <TableCell>
                    <ExecutionStatusBadge status={execution.status} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {execution.current_step ?? "—"}
                  </TableCell>
                  <TableCell>
                    <RiskBadge level={execution.latest_risk_level} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(execution.started_at), { addSuffix: true })}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(execution.updated_at), { addSuffix: true })}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
