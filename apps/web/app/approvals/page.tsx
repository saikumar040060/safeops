"use client";

import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Check, Loader2, ShieldQuestion, X } from "lucide-react";
import { toast } from "sonner";

import { ApprovalStatusBadge, RiskBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { RedactedFields } from "@/components/redacted-fields";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useApproveApproval, useApprovals, useRejectApproval } from "@/hooks/use-safeops";
import type { ApprovalRequest } from "@/lib/types";

const RESOLVER_NAME = "demo-operator";

export default function ApprovalsPage() {
  const { data, isLoading, error } = useApprovals();
  const [pendingAction, setPendingAction] = useState<{
    approval: ApprovalRequest;
    kind: "approve" | "reject";
  } | null>(null);

  const pending = (data ?? []).filter((a) => a.status === "PENDING");
  const resolved = (data ?? []).filter((a) => a.status !== "PENDING");

  return (
    <div>
      <PageHeader
        title="Approval Center"
        description="Human-in-the-loop review for actions the Policy or Risk Engine flagged."
      />

      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={3} />}

      {data && (
        <div className="flex flex-col gap-6">
          <section>
            <h2 className="mb-2 text-sm font-medium text-muted-foreground">
              Pending ({pending.length})
            </h2>
            {pending.length === 0 ? (
              <EmptyState title="Nothing pending" description="No actions currently need review." />
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {pending.map((approval) => (
                  <ApprovalCard
                    key={approval.id}
                    approval={approval}
                    onApprove={() => setPendingAction({ approval, kind: "approve" })}
                    onReject={() => setPendingAction({ approval, kind: "reject" })}
                  />
                ))}
              </div>
            )}
          </section>

          {resolved.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-medium text-muted-foreground">Resolved</h2>
              <div className="grid gap-3 md:grid-cols-2">
                {resolved.map((approval) => (
                  <ApprovalCard key={approval.id} approval={approval} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <ConfirmationDialog
        pendingAction={pendingAction}
        onClose={() => setPendingAction(null)}
      />
    </div>
  );
}

function ApprovalCard({
  approval,
  onApprove,
  onReject,
}: {
  approval: ApprovalRequest;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldQuestion className="size-4 text-muted-foreground" />
          <span className="font-mono text-sm font-semibold">{approval.tool_name}</span>
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge level={approval.risk_level} />
          <ApprovalStatusBadge status={approval.status} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground">{approval.reason}</p>
        <div>
          <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Arguments
          </p>
          <RedactedFields data={approval.approved_arguments} />
        </div>
        <p className="text-xs text-muted-foreground">
          Requested{" "}
          {formatDistanceToNow(new Date(approval.requested_at), { addSuffix: true })}
          {approval.status === "PENDING" &&
            ` · expires ${formatDistanceToNow(new Date(approval.expires_at), { addSuffix: true })}`}
        </p>
      </CardContent>
      {approval.status === "PENDING" && onApprove && onReject && (
        <CardFooter className="gap-2">
          <Button size="sm" onClick={onApprove}>
            <Check className="size-3.5" />
            Approve
          </Button>
          <Button size="sm" variant="outline" onClick={onReject}>
            <X className="size-3.5" />
            Reject
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}

function ConfirmationDialog({
  pendingAction,
  onClose,
}: {
  pendingAction: { approval: ApprovalRequest; kind: "approve" | "reject" } | null;
  onClose: () => void;
}) {
  const approveApproval = useApproveApproval();
  const rejectApproval = useRejectApproval();
  const isPending = approveApproval.isPending || rejectApproval.isPending;

  async function confirm() {
    if (!pendingAction) return;
    const { approval, kind } = pendingAction;
    try {
      if (kind === "approve") {
        await approveApproval.mutateAsync({ id: approval.id, resolvedBy: RESOLVER_NAME });
        toast.success(`Approved ${approval.tool_name}. It will execute exactly once.`);
      } else {
        await rejectApproval.mutateAsync({
          id: approval.id,
          resolvedBy: RESOLVER_NAME,
          reason: "Rejected from Approval Center",
        });
        toast.success(`Rejected ${approval.tool_name}.`);
      }
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Action failed.");
    }
  }

  return (
    <Dialog open={pendingAction !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        {pendingAction && (
          <>
            <DialogHeader>
              <DialogTitle>
                {pendingAction.kind === "approve" ? "Approve this action?" : "Reject this action?"}
              </DialogTitle>
              <DialogDescription>
                You are {pendingAction.kind === "approve" ? "approving" : "rejecting"} exactly
                this action. Arguments cannot be changed here.
              </DialogDescription>
            </DialogHeader>
            <div className="rounded-lg border bg-muted/40 p-3">
              <p className="font-mono text-sm font-semibold">{pendingAction.approval.tool_name}</p>
              <div className="mt-2">
                <RedactedFields data={pendingAction.approval.approved_arguments} />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={onClose} disabled={isPending}>
                Cancel
              </Button>
              <Button
                variant={pendingAction.kind === "approve" ? "default" : "destructive"}
                onClick={confirm}
                disabled={isPending}
              >
                {isPending && <Loader2 className="size-3.5 animate-spin" />}
                Confirm {pendingAction.kind === "approve" ? "approve" : "reject"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
