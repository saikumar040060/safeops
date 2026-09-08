import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const EXECUTION_STATUS_STYLES: Record<string, string> = {
  CREATED: "bg-muted text-muted-foreground border-border",
  RUNNING: "bg-blue-500/10 text-blue-600 border-blue-500/20 dark:text-blue-400",
  WAITING_APPROVAL: "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400",
  COMPLETED: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  FAILED: "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400",
  BLOCKED: "bg-red-600/10 text-red-700 border-red-600/20 dark:text-red-400",
  CANCELLED: "bg-muted text-muted-foreground border-border",
};

export function ExecutionStatusBadge({ status }: { status: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("font-medium tabular-nums", EXECUTION_STATUS_STYLES[status])}
    >
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

const RISK_STYLES: Record<string, string> = {
  LOW: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  MEDIUM: "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400",
  HIGH: "bg-orange-500/10 text-orange-600 border-orange-500/20 dark:text-orange-400",
  CRITICAL: "bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-400 font-semibold",
};

export function RiskBadge({ level }: { level: string | null | undefined }) {
  if (!level) {
    return (
      <Badge variant="outline" className="text-muted-foreground">
        —
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={cn(RISK_STYLES[level])}>
      {level}
    </Badge>
  );
}

const INCIDENT_STATUS_STYLES: Record<string, string> = {
  OPEN: "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400",
  RESOLVED: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  DISMISSED: "bg-muted text-muted-foreground border-border",
};

export function IncidentStatusBadge({ status }: { status: string }) {
  return <Badge variant="outline" className={cn(INCIDENT_STATUS_STYLES[status])}>{status}</Badge>;
}

const PERMISSION_STYLES: Record<string, string> = {
  ALLOW: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  DENY: "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400",
  CONDITIONAL: "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400",
};

export function PermissionBadge({ permission }: { permission: string }) {
  return <Badge variant="outline" className={cn(PERMISSION_STYLES[permission])}>{permission}</Badge>;
}

const APPROVAL_STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400",
  APPROVED: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  EXECUTED: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  REJECTED: "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400",
  EXPIRED: "bg-muted text-muted-foreground border-border",
};

export function ApprovalStatusBadge({ status }: { status: string }) {
  return <Badge variant="outline" className={cn(APPROVAL_STATUS_STYLES[status])}>{status}</Badge>;
}
