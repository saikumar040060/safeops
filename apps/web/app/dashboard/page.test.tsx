import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithQuery, jsonResponse } from "@/test-utils";
import type { DashboardSummary } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const SUMMARY: DashboardSummary = {
  metrics: {
    active_executions: 3,
    waiting_approvals: 2,
    blocked_actions: 1,
    open_security_incidents: 4,
    completed_executions: 7,
    risk_assessments_by_severity: [
      { severity: "LOW", count: 10 },
      { severity: "CRITICAL", count: 2 },
    ],
  },
  recent_executions: [
    {
      id: "exec-1",
      agent_id: "agent-1",
      objective: "Investigate duplicate payment for CUST-1001",
      status: "COMPLETED",
      initial_context: {},
      created_at: "2026-01-01T00:00:00Z",
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:01:00Z",
    },
  ],
  recent_approvals: [],
  recent_incidents: [],
  recent_blocked: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DashboardPage", () => {
  it("renders real metrics and recent activity from the backend, never fabricated numbers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(SUMMARY))
    );
    const { default: DashboardPage } = await import("@/app/dashboard/page");
    renderWithQuery(<DashboardPage />);

    expect(await screen.findByText("3")).toBeInTheDocument(); // active executions
    expect(screen.getByText("2")).toBeInTheDocument(); // waiting approvals
    expect(screen.getByText("7")).toBeInTheDocument(); // completed
    expect(
      screen.getByText("Investigate duplicate payment for CUST-1001")
    ).toBeInTheDocument();
  });
});
