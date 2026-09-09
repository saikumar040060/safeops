import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { AuthProvider } from "@/lib/auth";
import type { Operator } from "@/lib/types";

export function jsonResponse(body: unknown, init: { status?: number } = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
  });
}

const DEFAULT_TEST_OPERATOR: Operator = {
  id: "00000000-0000-0000-0000-000000000001",
  username: "test-operator",
  display_name: "Test Operator",
  role: "ADMIN",
  is_active: true,
};

/**
 * Renders with the same provider stack the app actually uses
 * (QueryClientProvider + AuthProvider), so components calling useAuth()
 * work in tests without every test file having to know that. By default
 * simulates a signed-in ADMIN (full permissions) so existing role-gated UI
 * (e.g. the Approve button) renders the way tests already expect; pass
 * `operator: null` to simulate a signed-out viewer instead, or a partial
 * Operator to test a specific role.
 */
export function renderWithQuery(
  ui: ReactElement,
  options: { operator?: Partial<Operator> | null } = {}
) {
  const operator =
    options.operator === null
      ? null
      : { ...DEFAULT_TEST_OPERATOR, ...(options.operator ?? {}) };

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  if (operator) {
    window.localStorage.setItem("safeops_token", "test-token");
    const underlyingFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/api/auth/me")) {
        return Promise.resolve(jsonResponse(operator));
      }
      return underlyingFetch(input, init);
    });
  } else {
    window.localStorage.removeItem("safeops_token");
  }

  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>
  );
}
