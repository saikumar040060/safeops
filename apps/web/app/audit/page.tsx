"use client";

import { useState } from "react";
import { format } from "date-fns";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { useAgents, useAuditEvents } from "@/hooks/use-safeops";

const EVENT_TYPES = [
  "EXECUTION_STARTED",
  "EXECUTION_STEP_STARTED",
  "EXECUTION_STEP_COMPLETED",
  "TOOL_REQUESTED",
  "PERMISSION_CHECKED",
  "POLICY_EVALUATION_STARTED",
  "POLICY_MATCHED",
  "POLICY_ALLOWED",
  "POLICY_APPROVAL_REQUIRED",
  "POLICY_BLOCKED",
  "RISK_ASSESSMENT_STARTED",
  "RISK_SIGNAL_DETECTED",
  "RISK_ASSESSED",
  "RISK_ESCALATED",
  "ACTION_ALLOWED",
  "ACTION_DENIED",
  "ACTION_BLOCKED_BY_RISK",
  "SECURITY_INCIDENT_CREATED",
  "APPROVAL_REQUESTED",
  "APPROVAL_APPROVED",
  "APPROVAL_REJECTED",
  "TOOL_EXECUTED",
  "TOOL_FAILED",
  "EXECUTION_WAITING_APPROVAL",
  "EXECUTION_RESUMED",
  "EXECUTION_COMPLETED",
  "EXECUTION_BLOCKED",
  "EXECUTION_FAILED",
  "EXECUTION_CANCELLED",
];

const ANY = "__any__";

export default function AuditPage() {
  const { data: agents } = useAgents();
  const [executionId, setExecutionId] = useState("");
  const [agentId, setAgentId] = useState<string>(ANY);
  const [eventType, setEventType] = useState<string>(ANY);

  const filters = {
    execution_id: executionId.trim() || undefined,
    agent_id: agentId === ANY ? undefined : agentId,
    event_type: eventType === ANY ? undefined : eventType,
  };

  const { data, isLoading, error, refetch, isFetching } = useAuditEvents(filters);

  return (
    <div>
      <PageHeader
        title="Audit"
        description="Chronological, tamper-evident event log — the authoritative replay of every decision."
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? "size-3.5 animate-spin" : "size-3.5"} />
            Refresh
          </Button>
        }
      />

      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <Input
          placeholder="Filter by execution ID"
          value={executionId}
          onChange={(e) => setExecutionId(e.target.value)}
          className="sm:max-w-xs font-mono text-xs"
        />
        <Select value={agentId} onValueChange={(v) => setAgentId(v ?? ANY)}>
          <SelectTrigger className="sm:w-48">
            <SelectValue placeholder="All agents" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>All agents</SelectItem>
            {agents?.map((agent) => (
              <SelectItem key={agent.id} value={agent.id}>
                {agent.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={eventType} onValueChange={(v) => setEventType(v ?? ANY)}>
          <SelectTrigger className="sm:w-56">
            <SelectValue placeholder="All event types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>All event types</SelectItem>
            {EVENT_TYPES.map((type) => (
              <SelectItem key={type} value={type} className="font-mono text-xs">
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={8} />}

      {data && data.length === 0 && (
        <EmptyState title="No matching audit events" description="Try clearing a filter." />
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Execution</TableHead>
                <TableHead>Seq</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((event) => (
                <TableRow key={event.id}>
                  <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                    {format(new Date(event.timestamp), "MMM d, HH:mm:ss")}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="font-mono">
                      {event.event_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">{event.actor}</TableCell>
                  <TableCell className="max-w-[10rem] truncate font-mono text-xs text-muted-foreground">
                    {event.execution_id}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {event.sequence}
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
