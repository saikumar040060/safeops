export type ExecutionStatus =
  | "CREATED"
  | "RUNNING"
  | "WAITING_APPROVAL"
  | "COMPLETED"
  | "FAILED"
  | "BLOCKED"
  | "CANCELLED";

export type StepType = "PLAN" | "TOOL_CALL" | "TOOL_RESULT" | "APPROVAL_WAIT" | "FINAL";
export type StepStatus = "PENDING" | "COMPLETED" | "WAITING_APPROVAL" | "BLOCKED" | "FAILED";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type PolicyAction = "ALLOW" | "REQUIRE_APPROVAL" | "BLOCK";
export type PermissionType = "ALLOW" | "DENY" | "CONDITIONAL";
export type AgentStatus = "ACTIVE" | "DISABLED";
export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "EXECUTED";
export type IncidentStatus = "OPEN" | "RESOLVED" | "DISMISSED";
export type IncidentType =
  | "PROMPT_INJECTION"
  | "DATA_EXFILTRATION"
  | "SCOPE_DEVIATION"
  | "SENSITIVE_DATA_ACCESS"
  | "PRIVILEGE_ESCALATION"
  | "DESTRUCTIVE_ACTION"
  | "EXTERNAL_COMMUNICATION"
  | "FINANCIAL_RISK"
  | "UNUSUAL_TOOL_SEQUENCE";

export type OperatorRole = "VIEWER" | "OPERATOR" | "APPROVER" | "ADMIN";

export type Operator = {
  id: string;
  username: string;
  display_name: string;
  role: OperatorRole;
  is_active: boolean;
};

export type PublicConfig = {
  demo_mode: boolean;
  environment: string;
};

export type Agent = {
  id: string;
  name: string;
  type: string;
  description: string | null;
  status: AgentStatus;
  risk_level: RiskLevel;
  created_at: string;
  updated_at: string;
};

export type ToolPermissionSummary = {
  tool_id: string;
  tool_name: string;
  permission: PermissionType;
  risk_category: RiskLevel;
};

export type ExecutionBrief = {
  id: string;
  objective: string;
  status: string;
  created_at: string;
  completed_at: string | null;
};

export type AgentDetail = Agent & {
  permissions: ToolPermissionSummary[];
  recent_executions: ExecutionBrief[];
};

export type Execution = {
  id: string;
  agent_id: string;
  objective: string;
  status: ExecutionStatus;
  initial_context: Record<string, unknown>;
  created_at: string;
  started_at: string;
  completed_at: string | null;
};

export type ExecutionSummary = Execution & {
  current_step: string | null;
  latest_risk_level: string | null;
  updated_at: string;
};

export type ExecutionStep = {
  id: string;
  execution_id: string;
  sequence: number;
  step_type: StepType;
  status: StepStatus;
  tool_request_id: string | null;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
};

export type AuditEvent = {
  id: string;
  execution_id: string;
  sequence: number;
  event_type: string;
  actor: string;
  event_metadata: Record<string, unknown>;
  timestamp: string;
};

export type ExecutionTimeline = {
  execution: Execution;
  steps: ExecutionStep[];
  audit_events: AuditEvent[];
};

export type ApprovalRequest = {
  id: string;
  execution_id: string;
  agent_id: string;
  tool_request_id: string;
  policy_decision_id: string;
  tool_name: string;
  approved_arguments: Record<string, unknown>;
  risk_level: RiskLevel;
  reason: string;
  status: ApprovalStatus;
  requested_at: string;
  expires_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  executed_at: string | null;
};

export type ApprovalActionResult = {
  status: string;
  approval_id: string | null;
  approval_status: string | null;
  tool_result: Record<string, unknown> | null;
  reason: string | null;
};

export type SecurityIncident = {
  id: string;
  execution_id: string;
  agent_id: string;
  tool_request_id: string;
  risk_assessment_id: string;
  incident_type: IncidentType;
  severity: RiskLevel;
  title: string;
  description: string;
  indicators: string[];
  status: IncidentStatus;
  created_at: string;
  resolved_at: string | null;
};

export type SeverityCount = {
  severity: string;
  count: number;
};

export type DashboardMetrics = {
  active_executions: number;
  waiting_approvals: number;
  blocked_actions: number;
  open_security_incidents: number;
  completed_executions: number;
  risk_assessments_by_severity: SeverityCount[];
};

export type DashboardSummary = {
  metrics: DashboardMetrics;
  recent_executions: Execution[];
  recent_approvals: ApprovalRequest[];
  recent_incidents: SecurityIncident[];
  recent_blocked: AuditEvent[];
};

export type RuntimeResult = {
  status: string;
  execution_status: string;
  execution_id: string | null;
  reason: string | null;
  tool_name: string | null;
  approval_request_id: string | null;
  step_sequence: number | null;
};

export const TERMINAL_EXECUTION_STATUSES: ExecutionStatus[] = [
  "COMPLETED",
  "FAILED",
  "BLOCKED",
  "CANCELLED",
];

export function isTerminalStatus(status: ExecutionStatus): boolean {
  return TERMINAL_EXECUTION_STATUSES.includes(status);
}
