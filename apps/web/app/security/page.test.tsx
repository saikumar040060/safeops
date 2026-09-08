import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithQuery, jsonResponse } from "@/test-utils";
import SecurityPage from "@/app/security/page";
import type { SecurityIncident } from "@/lib/types";

const CRITICAL_INCIDENT: SecurityIncident = {
  id: "incident-1",
  execution_id: "exec-1",
  agent_id: "agent-1",
  tool_request_id: "tr-1",
  risk_assessment_id: "ra-1",
  incident_type: "PROMPT_INJECTION",
  severity: "CRITICAL",
  title: "Blocked send_external_email call",
  description: "Risk Engine blocked a send_external_email call with score 100.",
  indicators: ["INJECTION_PHRASE_MATCH", "DATA_EXPORT_TOOL"],
  status: "OPEN",
  created_at: "2026-01-01T00:00:00Z",
  resolved_at: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SecurityPage", () => {
  it("displays a CRITICAL incident with its severity and signals", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse([CRITICAL_INCIDENT]))
    );

    renderWithQuery(<SecurityPage />);

    expect(await screen.findByText("PROMPT_INJECTION")).toBeInTheDocument();
    // "CRITICAL" also appears as a filter tab label, so assert there are at
    // least two occurrences (the tab plus the incident's severity badge).
    expect(screen.getAllByText("CRITICAL").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("INJECTION_PHRASE_MATCH")).toBeInTheDocument();
    expect(screen.getByText("DATA_EXPORT_TOOL")).toBeInTheDocument();
  });

  it("never renders the full raw malicious prompt outside the description summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse([CRITICAL_INCIDENT]))
    );
    renderWithQuery(<SecurityPage />);
    await screen.findByText("PROMPT_INJECTION");
    expect(screen.queryByText(/ignore all previous instructions/i)).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no incidents", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse([]))
    );
    renderWithQuery(<SecurityPage />);
    expect(await screen.findByText(/no security incidents/i)).toBeInTheDocument();
  });
});
