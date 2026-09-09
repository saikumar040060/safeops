import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { renderWithQuery, jsonResponse } from "@/test-utils";
import ApprovalsPage from "@/app/approvals/page";
import type { ApprovalRequest } from "@/lib/types";

const PENDING_APPROVAL: ApprovalRequest = {
  id: "approval-1",
  execution_id: "exec-1",
  agent_id: "agent-1",
  tool_request_id: "tr-1",
  policy_decision_id: "pd-1",
  tool_name: "refund_payment",
  approved_arguments: { payment_id: "PAY-9001", amount: "750.00", reason: "Duplicate charge" },
  risk_level: "LOW",
  reason: "Matched policy 'SUPPORT_REFUND_APPROVAL'",
  status: "PENDING",
  requested_at: "2026-01-01T00:00:00Z",
  expires_at: "2026-01-01T00:15:00Z",
  resolved_at: null,
  resolved_by: null,
  executed_at: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(approvals: ApprovalRequest[]) {
  const calls: Array<{ url: string; method: string; body: unknown; authorization: string | null }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const headers = new Headers(init?.headers);
    calls.push({
      url,
      method,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      authorization: headers.get("Authorization"),
    });

    if (url.endsWith("/api/approvals") && method === "GET") {
      return jsonResponse(approvals);
    }
    if (url.includes("/approve")) {
      return jsonResponse({
        status: "EXECUTED",
        approval_id: "approval-1",
        approval_status: "EXECUTED",
        tool_result: { payment_id: "PAY-9001", refund_amount: "750.00" },
        reason: null,
      });
    }
    if (url.includes("/reject")) {
      return jsonResponse({
        status: "REJECTED",
        approval_id: "approval-1",
        approval_status: "REJECTED",
        tool_result: null,
        reason: null,
      });
    }
    return jsonResponse({ detail: "not found" }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

describe("ApprovalsPage", () => {
  it("renders a pending approval request with its exact frozen arguments", async () => {
    stubFetch([PENDING_APPROVAL]);
    renderWithQuery(<ApprovalsPage />);

    expect(await screen.findByText("refund_payment")).toBeInTheDocument();
    expect(screen.getByText("PAY-9001")).toBeInTheDocument();
    expect(screen.getByText("750.00")).toBeInTheDocument();
  });

  it("never renders an editable input for the tool arguments", async () => {
    stubFetch([PENDING_APPROVAL]);
    renderWithQuery(<ApprovalsPage />);

    await screen.findByText("refund_payment");
    // The arguments are shown as read-only <dd> text via RedactedFields --
    // there must be no text input/textarea anywhere a human could type a
    // replacement value for payment_id/amount/reason.
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });

  it("approve button never sends a resolver identity in the body -- it comes from the auth header", async () => {
    const { calls } = stubFetch([PENDING_APPROVAL]);
    renderWithQuery(<ApprovalsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /approve/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm approve/i }));

    await waitFor(() => {
      const approveCall = calls.find((c) => c.url.includes("/approve"));
      expect(approveCall).toBeDefined();
      expect(approveCall?.body).toEqual({});
      expect(approveCall?.authorization).toBe("Bearer test-token");
    });
  });

  it("reject button calls the reject endpoint with only a reason, never an identity", async () => {
    const { calls } = stubFetch([PENDING_APPROVAL]);
    renderWithQuery(<ApprovalsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /reject/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm reject/i }));

    await waitFor(() => {
      const rejectCall = calls.find((c) => c.url.includes("/reject"));
      expect(rejectCall).toBeDefined();
      expect(rejectCall?.body).toEqual({ reason: "Rejected from Approval Center" });
      expect(rejectCall?.authorization).toBe("Bearer test-token");
    });
  });

  it("does not render approve/reject controls for a VIEWER -- backend still enforces independently", async () => {
    stubFetch([PENDING_APPROVAL]);
    renderWithQuery(<ApprovalsPage />, { operator: { role: "VIEWER" } });

    await screen.findByText("refund_payment");
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();
  });

  it("shows an empty state when there is nothing pending", async () => {
    stubFetch([]);
    renderWithQuery(<ApprovalsPage />);
    expect(await screen.findByText(/nothing pending/i)).toBeInTheDocument();
  });
});
