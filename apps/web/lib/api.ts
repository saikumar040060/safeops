import type {
  Agent,
  AgentDetail,
  ApprovalActionResult,
  ApprovalRequest,
  AuditEvent,
  DashboardSummary,
  ExecutionSummary,
  Execution,
  ExecutionStep,
  ExecutionTimeline,
  RuntimeResult,
  SecurityIncident,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("Cannot reach the SafeOps backend.", 0);
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        message = body.detail;
      } else if (body?.detail?.reason) {
        message = body.detail.reason;
      }
    } catch {
      // fall through to default message; never surface raw backend/network internals
    }
    throw new ApiError(message, res.status);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export type HealthResponse = { status: string };
export function fetchHealth(): Promise<HealthResponse> {
  return request("/api/health");
}

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return request("/api/dashboard/summary");
}

export function fetchAgents(): Promise<Agent[]> {
  return request("/api/agents");
}

export function fetchAgent(id: string): Promise<AgentDetail> {
  return request(`/api/agents/${id}`);
}

export function fetchExecutions(filters: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<ExecutionSummary[]> {
  return request(`/api/executions${query(filters)}`);
}

export function fetchExecution(id: string): Promise<Execution> {
  return request(`/api/executions/${id}`);
}

export function fetchExecutionSteps(id: string): Promise<ExecutionStep[]> {
  return request(`/api/executions/${id}/steps`);
}

export function fetchExecutionTimeline(id: string): Promise<ExecutionTimeline> {
  return request(`/api/executions/${id}/timeline`);
}

export function startExecution(body: {
  agent_id: string;
  objective: string;
}): Promise<RuntimeResult> {
  return request("/api/executions", { method: "POST", body: JSON.stringify(body) });
}

export function stepExecution(id: string): Promise<RuntimeResult> {
  return request(`/api/executions/${id}/step`, { method: "POST" });
}

export function resumeExecution(id: string): Promise<RuntimeResult> {
  return request(`/api/executions/${id}/resume`, { method: "POST" });
}

export function cancelExecution(id: string): Promise<RuntimeResult> {
  return request(`/api/executions/${id}/cancel`, { method: "POST" });
}

export function fetchApprovals(): Promise<ApprovalRequest[]> {
  return request("/api/approvals");
}

export function fetchApproval(id: string): Promise<ApprovalRequest> {
  return request(`/api/approvals/${id}`);
}

export function approveApproval(id: string, resolvedBy: string): Promise<ApprovalActionResult> {
  return request(`/api/approvals/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ resolved_by: resolvedBy }),
  });
}

export function rejectApproval(
  id: string,
  resolvedBy: string,
  reason?: string
): Promise<ApprovalActionResult> {
  return request(`/api/approvals/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ resolved_by: resolvedBy, reason }),
  });
}

export function fetchSecurityIncidents(filters: {
  severity?: string;
  status?: string;
}): Promise<SecurityIncident[]> {
  return request(`/api/security/incidents${query(filters)}`);
}

export function fetchSecurityIncident(id: string): Promise<SecurityIncident> {
  return request(`/api/security/incidents/${id}`);
}

export function fetchAuditEvents(filters: {
  execution_id?: string;
  agent_id?: string;
  event_type?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditEvent[]> {
  return request(`/api/audit${query(filters)}`);
}

export function fetchExecutionAuditEvents(executionId: string): Promise<AuditEvent[]> {
  return request(`/api/audit/executions/${executionId}`);
}
