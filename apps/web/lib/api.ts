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
  Operator,
  PublicConfig,
  RuntimeResult,
  SecurityIncident,
} from "@/lib/types";
import { clearStoredToken, getStoredToken } from "@/lib/auth-storage";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Requests to these paths never trigger the global "session expired, go to
// /login" redirect on a 401 -- they are the auth-check calls themselves
// (the login page validating a freshly entered token, or the public config
// probe), and forcing a redirect there would either loop or fire before
// the user has had a chance to enter a token at all.
const AUTH_PROBE_PATHS = new Set(["/api/auth/me"]);

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

function extractMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { reason?: unknown; message?: unknown };
    if (typeof d.reason === "string") return d.reason;
    if (typeof d.message === "string") return d.message;
  }
  return `Request failed (${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("Cannot reach the SafeOps backend.", 0);
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    let body: unknown;
    try {
      body = await res.json();
      message = extractMessage(body, res.status);
    } catch {
      // fall through to default message; never surface raw backend/network internals
    }

    if (res.status === 401 && !AUTH_PROBE_PATHS.has(path) && typeof window !== "undefined") {
      // The stored token is missing/invalid/expired/revoked -- there is no
      // way to recover within this request, so clear it and send the
      // viewer to log in again. A hard navigation (not router.push) so
      // this works even from contexts outside the React tree.
      clearStoredToken();
      if (window.location.pathname !== "/login") {
        // This module runs outside the React tree (no useRouter available);
        // a hard navigation is also correct here, clearing all client-side
        // state on session expiry.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = "/login";
      }
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

// Approver identity is never supplied by the caller -- the backend derives
// it entirely from the authenticated bearer token (app.core.security). No
// resolvedBy parameter exists here for exactly that reason.
export function approveApproval(id: string): Promise<ApprovalActionResult> {
  return request(`/api/approvals/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function rejectApproval(id: string, reason?: string): Promise<ApprovalActionResult> {
  return request(`/api/approvals/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
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

export function fetchPublicConfig(): Promise<PublicConfig> {
  return request("/api/auth/config");
}

/** Validates a raw token by asking the backend who it belongs to -- never
 * decoded or trusted client-side, the backend is the only authority. */
export function fetchCurrentOperator(): Promise<Operator> {
  return request("/api/auth/me");
}
