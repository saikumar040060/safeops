import { format } from "date-fns";

import { Badge } from "@/components/ui/badge";
import type { AuditEvent } from "@/lib/types";

const SEVERITY_EVENT_TYPES = new Set([
  "ACTION_DENIED",
  "ACTION_BLOCKED",
  "ACTION_BLOCKED_BY_RISK",
  "POLICY_BLOCKED",
  "EXECUTION_BLOCKED",
  "EXECUTION_FAILED",
  "SECURITY_INCIDENT_CREATED",
]);

export function AuditTrail({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">No audit events yet.</p>;
  }

  return (
    <ol className="flex flex-col gap-1">
      {events.map((event) => (
        <li
          key={event.id}
          className="flex items-center gap-3 rounded-md border-b px-2 py-1.5 text-xs last:border-b-0"
        >
          <span className="w-8 shrink-0 text-right font-mono text-muted-foreground">
            #{event.sequence}
          </span>
          <span className="w-20 shrink-0 font-mono text-muted-foreground">
            {format(new Date(event.timestamp), "HH:mm:ss")}
          </span>
          <Badge
            variant={SEVERITY_EVENT_TYPES.has(event.event_type) ? "destructive" : "outline"}
            className="shrink-0 font-mono"
          >
            {event.event_type}
          </Badge>
          <span className="truncate text-muted-foreground">{event.actor}</span>
        </li>
      ))}
    </ol>
  );
}
