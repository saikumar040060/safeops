import { describe, expect, it } from "vitest";

import { isSensitiveKey, redactEntries, redactedLabel } from "@/lib/redact";

describe("isSensitiveKey", () => {
  it.each([
    "password",
    "Password",
    "api_key",
    "apiKey",
    "api-key",
    "token",
    "access_token",
    "secret",
    "client_secret",
    "private_key",
    "credential",
    "authorization",
  ])("flags %s as sensitive", (key) => {
    expect(isSensitiveKey(key)).toBe(true);
  });

  it.each(["payment_id", "amount", "reason", "customer_id", "service_name", "version"])(
    "does not flag %s as sensitive",
    (key) => {
      expect(isSensitiveKey(key)).toBe(false);
    }
  );
});

describe("redactEntries", () => {
  it("masks sensitive keys regardless of value", () => {
    const entries = redactEntries({ password: "hunter2", api_key: "sk-live-abc123" });
    expect(entries).toEqual([
      { key: "password", value: redactedLabel(), redacted: true },
      { key: "api_key", value: redactedLabel(), redacted: true },
    ]);
  });

  it("passes through non-sensitive values", () => {
    const entries = redactEntries({ payment_id: "PAY-9002", amount: "750.00" });
    expect(entries).toEqual([
      { key: "payment_id", value: "PAY-9002", redacted: false },
      { key: "amount", value: "750.00", redacted: false },
    ]);
  });

  it("never leaks a sensitive value into the rendered output", () => {
    const entries = redactEntries({ secret_token: "super-secret-value" });
    const serialized = JSON.stringify(entries);
    expect(serialized).not.toContain("super-secret-value");
  });

  it("returns an empty list for null/undefined input", () => {
    expect(redactEntries(null)).toEqual([]);
    expect(redactEntries(undefined)).toEqual([]);
  });
});
