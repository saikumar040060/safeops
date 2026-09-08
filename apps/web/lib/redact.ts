const REDACTED = "••••••";

const SENSITIVE_KEY_PATTERN =
  /pass(word)?|secret|token|api[_-]?key|private[_-]?key|credential|authorization|access[_-]?key/i;

export function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEY_PATTERN.test(key);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Shallow-redacts a plain object for display: any key that looks like a
 * secret (password/token/api key/credential/...) is masked regardless of
 * its value. Never mutates the input. This is a display-layer safety net
 * only -- the backend already never leaks raw untrusted prompt text or
 * secrets into audit metadata; this exists for defense in depth and for
 * any future tool argument that legitimately carries a sensitive-looking
 * field name.
 */
export function redactEntries(
  data: Record<string, unknown> | null | undefined
): Array<{ key: string; value: string; redacted: boolean }> {
  if (!data) return [];
  return Object.entries(data).map(([key, value]) => {
    if (isSensitiveKey(key)) {
      return { key, value: REDACTED, redacted: true };
    }
    return { key, value: formatValue(value), redacted: false };
  });
}

export function redactedLabel(): string {
  return REDACTED;
}

/** Truncates long free-text safely for compact table/card display. */
export function truncate(text: string, max = 140): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}
