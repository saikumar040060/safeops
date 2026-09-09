export const queryKeys = {
  health: ["health"] as const,
  publicConfig: ["auth", "config"] as const,
  dashboard: ["dashboard", "summary"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  executions: (filters: Record<string, unknown> = {}) => ["executions", filters] as const,
  execution: (id: string) => ["executions", id] as const,
  executionTimeline: (id: string) => ["executions", id, "timeline"] as const,
  approvals: ["approvals"] as const,
  approval: (id: string) => ["approvals", id] as const,
  securityIncidents: (filters: Record<string, unknown> = {}) =>
    ["security", "incidents", filters] as const,
  securityIncident: (id: string) => ["security", "incidents", id] as const,
  audit: (filters: Record<string, unknown> = {}) => ["audit", filters] as const,
};
