"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import * as api from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { isTerminalStatus, type ExecutionStatus } from "@/lib/types";

export function usePublicConfig() {
  return useQuery({
    queryKey: queryKeys.publicConfig,
    queryFn: api.fetchPublicConfig,
    staleTime: Infinity,
  });
}

export function useDashboardSummary() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: api.fetchDashboardSummary,
    refetchInterval: 5000,
  });
}

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents,
    queryFn: api.fetchAgents,
  });
}

export function useAgent(id: string) {
  return useQuery({
    queryKey: queryKeys.agent(id),
    queryFn: () => api.fetchAgent(id),
    refetchInterval: 8000,
  });
}

export function useExecutions(filters: { status?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.executions(filters),
    queryFn: () => api.fetchExecutions(filters),
    refetchInterval: 4000,
  });
}

export function useExecution(id: string) {
  return useQuery({
    queryKey: queryKeys.execution(id),
    queryFn: () => api.fetchExecution(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isTerminalStatus(status) ? false : 2000;
    },
  });
}

export function useExecutionTimeline(id: string) {
  return useQuery({
    queryKey: queryKeys.executionTimeline(id),
    queryFn: () => api.fetchExecutionTimeline(id),
    refetchInterval: (query) => {
      const status = query.state.data?.execution.status;
      return status && isTerminalStatus(status) ? false : 2000;
    },
  });
}

export function useStartExecution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.startExecution,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["executions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useStepExecution(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.stepExecution(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.execution(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.executionTimeline(id) });
      queryClient.invalidateQueries({ queryKey: ["executions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals });
    },
  });
}

export function useResumeExecution(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.resumeExecution(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.execution(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.executionTimeline(id) });
      queryClient.invalidateQueries({ queryKey: ["executions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useCancelExecution(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.cancelExecution(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.execution(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.executionTimeline(id) });
      queryClient.invalidateQueries({ queryKey: ["executions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useApprovals() {
  return useQuery({
    queryKey: queryKeys.approvals,
    queryFn: api.fetchApprovals,
    refetchInterval: 3000,
  });
}

export function useApproveApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => api.approveApproval(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals });
      queryClient.invalidateQueries({ queryKey: ["executions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useRejectApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      api.rejectApproval(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals });
      queryClient.invalidateQueries({ queryKey: ["executions"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useSecurityIncidents(filters: { severity?: string; status?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.securityIncidents(filters),
    queryFn: () => api.fetchSecurityIncidents(filters),
    refetchInterval: 5000,
  });
}

export function useSecurityIncident(id: string) {
  return useQuery({
    queryKey: queryKeys.securityIncident(id),
    queryFn: () => api.fetchSecurityIncident(id),
  });
}

export function useAuditEvents(
  filters: { execution_id?: string; agent_id?: string; event_type?: string } = {}
) {
  return useQuery({
    queryKey: queryKeys.audit(filters),
    queryFn: () => api.fetchAuditEvents(filters),
  });
}

/**
 * Drives a RUNNING execution forward by calling the real step()/resume()
 * endpoints on an interval -- this is the only thing that makes progress
 * happen; nothing about execution state is ever simulated client-side.
 * Stops automatically once the execution leaves RUNNING (waiting for
 * approval, blocked, failed, completed, or cancelled) or on unmount.
 *
 * `hasUnresolvedWaitingStep` must be true when the latest ExecutionStep is
 * still marked WAITING_APPROVAL even though the execution itself is back to
 * RUNNING -- that's the brief window right after a human resolves the
 * approval (ApprovalEngine already flipped Execution back to RUNNING, but
 * the step's own outcome hasn't been reconciled yet). In that window only
 * resume() finalizes the step's true outcome before continuing the plan;
 * calling step() there would silently skip that reconciliation and leave
 * the timeline showing the approved step stuck at "waiting approval"
 * forever, even though the backend already executed it correctly.
 */
export function useAutoStep(
  executionId: string,
  status: ExecutionStatus | undefined,
  hasUnresolvedWaitingStep: boolean
) {
  const queryClient = useQueryClient();
  const inFlight = useRef(false);

  useEffect(() => {
    if (status !== "RUNNING") return;

    const interval = setInterval(async () => {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        if (hasUnresolvedWaitingStep) {
          await api.resumeExecution(executionId);
        } else {
          await api.stepExecution(executionId);
        }
      } catch {
        // A transient failure here just means we retry on the next tick;
        // the execution/timeline queries below still reflect real state.
      } finally {
        inFlight.current = false;
        queryClient.invalidateQueries({ queryKey: queryKeys.execution(executionId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.executionTimeline(executionId) });
        queryClient.invalidateQueries({ queryKey: ["executions"] });
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [executionId, status, hasUnresolvedWaitingStep, queryClient]);
}
