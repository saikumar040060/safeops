import Link from "next/link";
import { format } from "date-fns";
import { CheckCircle2, CircleDashed, Clock, ShieldBan, XCircle } from "lucide-react";

import { ApprovalStatusBadge, ExecutionStatusBadge, RiskBadge } from "@/components/badges";
import { RedactedFields } from "@/components/redacted-fields";
import { Badge } from "@/components/ui/badge";
import type { ExecutionStep } from "@/lib/types";

function StepIcon({ status }: { status: string }) {
  switch (status) {
    case "COMPLETED":
      return <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" />;
    case "BLOCKED":
      return <ShieldBan className="size-4 text-red-600 dark:text-red-400" />;
    case "FAILED":
      return <XCircle className="size-4 text-red-600 dark:text-red-400" />;
    case "WAITING_APPROVAL":
      return <Clock className="size-4 text-amber-600 dark:text-amber-400" />;
    default:
      return <CircleDashed className="size-4 text-muted-foreground" />;
  }
}

function stepTitle(step: ExecutionStep): string {
  if (step.step_type === "FINAL") {
    const decision = (step.input as { decision?: string }).decision;
    return decision === "COMPLETE" ? "Execution completed" : "Execution failed";
  }
  const toolName = (step.input as { tool_name?: string }).tool_name;
  return toolName ?? step.step_type;
}

export function ExecutionTimelineView({ steps }: { steps: ExecutionStep[] }) {
  if (steps.length === 0) {
    return <p className="text-sm text-muted-foreground">No steps have run yet.</p>;
  }

  return (
    <ol className="flex flex-col gap-0">
      {steps.map((step, index) => {
        const output = (step.output ?? {}) as Record<string, unknown>;
        const input = step.input as {
          tool_name?: string;
          reason?: string;
          arguments?: Record<string, unknown>;
          sources?: Array<{ type: string; trust: string; content: string }>;
        };
        const isLast = index === steps.length - 1;
        const riskSignals = (output.risk_signals as string[] | undefined) ?? [];

        return (
          <li key={step.id} className="relative flex gap-3 pb-6 last:pb-0">
            {!isLast && (
              <span className="absolute top-6 left-[7px] h-full w-px bg-border" aria-hidden />
            )}
            <div className="z-10 mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full bg-background">
              <StepIcon status={step.status} />
            </div>
            <div className="min-w-0 flex-1 rounded-lg border bg-card p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium">{stepTitle(step)}</span>
                  <Badge variant="secondary">seq {step.sequence}</Badge>
                  {step.source !== "internal" && (
                    <Badge
                      variant="outline"
                      className="border-sky-500/30 text-sky-600 dark:text-sky-400"
                      title={step.integration_name ?? undefined}
                    >
                      {step.source === "external_mcp" ? "MCP" : "External API"}
                      {step.integration_name ? ` · ${step.integration_name}` : ""}
                    </Badge>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {format(new Date(step.completed_at ?? step.created_at), "HH:mm:ss")}
                </span>
              </div>

              {input.reason && (
                <p className="mt-1 text-xs text-muted-foreground">{input.reason}</p>
              )}

              {input.sources && input.sources.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {input.sources.map((source, i) => (
                    <Badge
                      key={i}
                      variant="outline"
                      className={
                        source.trust === "UNTRUSTED"
                          ? "border-amber-500/30 text-amber-600 dark:text-amber-400"
                          : "border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                      }
                    >
                      {source.trust}: {source.type}
                    </Badge>
                  ))}
                </div>
              )}

              {input.arguments && Object.keys(input.arguments).length > 0 && (
                <div className="mt-2">
                  <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    Arguments
                  </p>
                  <RedactedFields data={input.arguments} />
                </div>
              )}

              {(output.decision ||
                output.risk_level ||
                output.approval_request_id ||
                riskSignals.length > 0) && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {typeof output.decision === "string" && (
                    <Badge variant="outline">{output.decision}</Badge>
                  )}
                  {typeof output.risk_level === "string" && (
                    <span className="flex items-center gap-1 text-xs">
                      Risk <RiskBadge level={output.risk_level} />
                      {typeof output.risk_score === "number" && (
                        <span className="text-muted-foreground">({output.risk_score})</span>
                      )}
                    </span>
                  )}
                  {riskSignals.map((signal) => (
                    <Badge key={signal} variant="destructive">
                      {signal}
                    </Badge>
                  ))}
                  {typeof output.approval_request_id === "string" && (
                    <Link
                      href="/approvals"
                      className="text-xs font-medium text-primary underline-offset-2 hover:underline"
                    >
                      View approval →
                    </Link>
                  )}
                </div>
              )}

              {typeof output.resolution === "string" && (
                <div className="mt-2">
                  <ApprovalStatusBadge
                    status={output.resolution === "EXECUTED" ? "EXECUTED" : output.resolution}
                  />
                </div>
              )}

              {output.tool_result != null &&
                typeof output.tool_result === "object" &&
                Object.keys(output.tool_result as object).length > 0 && (
                  <div className="mt-2">
                    <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                      Result
                    </p>
                    <RedactedFields data={output.tool_result as Record<string, unknown>} />
                  </div>
                )}

              {typeof output.reason === "string" && step.status !== "COMPLETED" && (
                <p className="mt-2 text-xs text-muted-foreground">{output.reason}</p>
              )}

              <div className="mt-2">
                <ExecutionStatusBadgeForStep status={step.status} />
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function ExecutionStatusBadgeForStep({ status }: { status: string }) {
  // Reuses the same color language as execution status badges even though
  // step status values differ slightly (PENDING/WAITING_APPROVAL/etc.).
  return <ExecutionStatusBadge status={status} />;
}
