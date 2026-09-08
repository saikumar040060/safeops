"use client";

import Link from "next/link";
import { ArrowLeft, Ban, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingBlock } from "@/components/states";
import { ExecutionStatusBadge } from "@/components/badges";
import { AuditTrail } from "@/components/execution/audit-trail";
import { ExecutionTimelineView } from "@/components/execution/execution-timeline";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAgents, useAutoStep, useCancelExecution, useExecutionTimeline } from "@/hooks/use-safeops";
import { isTerminalStatus } from "@/lib/types";

export function ExecutionDetailView({ executionId }: { executionId: string }) {
  const { data: timeline, isLoading, error } = useExecutionTimeline(executionId);
  const { data: agents } = useAgents();
  const cancelExecution = useCancelExecution(executionId);

  const latestStep = timeline?.steps.at(-1);
  const hasUnresolvedWaitingStep = latestStep?.status === "WAITING_APPROVAL";
  useAutoStep(executionId, timeline?.execution.status, hasUnresolvedWaitingStep);

  const execution = timeline?.execution;
  const agent = agents?.find((a) => a.id === execution?.agent_id);

  async function handleCancel() {
    try {
      const result = await cancelExecution.mutateAsync();
      if (result.status === "CANCELLED") {
        toast.success("Execution cancelled.");
      } else {
        toast.info(result.reason ?? "Execution could not be cancelled.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to cancel execution.");
    }
  }

  return (
    <div>
      <Button variant="ghost" size="sm" className="mb-2" render={<Link href="/executions" />}>
        <ArrowLeft className="size-3.5" />
        Executions
      </Button>

      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={5} />}

      {execution && (
        <>
          <PageHeader
            title={execution.objective}
            description={agent ? `Agent: ${agent.name}` : undefined}
            actions={
              <>
                <ExecutionStatusBadge status={execution.status} />
                {!isTerminalStatus(execution.status) && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={cancelExecution.isPending}
                    onClick={handleCancel}
                  >
                    {cancelExecution.isPending ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Ban className="size-3.5" />
                    )}
                    Cancel
                  </Button>
                )}
              </>
            }
          />

          {execution.status === "WAITING_APPROVAL" && (
            <Alert className="mb-4 border-amber-500/30 bg-amber-500/5">
              <AlertTitle>Waiting for human approval</AlertTitle>
              <AlertDescription>
                This execution is paused. Resolve the pending request from the{" "}
                <Link href="/approvals" className="font-medium underline underline-offset-2">
                  Approval Center
                </Link>{" "}
                to continue.
              </AlertDescription>
            </Alert>
          )}

          {execution.status === "BLOCKED" && (
            <Alert variant="destructive" className="mb-4">
              <AlertTitle>Execution blocked by the Risk Engine</AlertTitle>
              <AlertDescription>
                A proposed action was blocked before it could run. Check the{" "}
                <Link href="/security" className="font-medium underline underline-offset-2">
                  Security Center
                </Link>{" "}
                for the incident.
              </AlertDescription>
            </Alert>
          )}

          <Card>
            <CardContent>
              <Tabs defaultValue="timeline">
                <TabsList className="mb-4">
                  <TabsTrigger value="timeline">Timeline</TabsTrigger>
                  <TabsTrigger value="audit">Audit trail</TabsTrigger>
                </TabsList>
                <TabsContent value="timeline">
                  <ExecutionTimelineView steps={timeline?.steps ?? []} />
                </TabsContent>
                <TabsContent value="audit">
                  <AuditTrail events={timeline?.audit_events ?? []} />
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
