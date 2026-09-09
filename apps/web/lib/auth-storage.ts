const TOKEN_KEY = "safeops_token";

/**
 * Per-viewer token storage only -- never sent anywhere but the
 * Authorization header on requests to the SafeOps API (see lib/api.ts).
 * Wrapped in try/catch: localStorage can throw (private browsing, storage
 * disabled) and the app must still render correctly with no stored value.
 */

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage unavailable -- the session simply won't persist across reloads.
  }
}

export function clearStoredToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing to clean up if storage was never reachable.
  }
}
