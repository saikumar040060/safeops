"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { fetchCurrentOperator } from "@/lib/api";
import { clearStoredToken, getStoredToken, setStoredToken } from "@/lib/auth-storage";
import type { Operator, OperatorRole } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type LoginResult = { ok: true } | { ok: false; error: string };

type AuthContextValue = {
  status: AuthStatus;
  operator: Operator | null;
  login: (token: string) => Promise<LoginResult>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Client-side auth state. Never decodes or trusts a token itself -- the
 * only thing it ever does with a token is hand it to the backend
 * (`GET /api/auth/me`) and store whatever operator identity/role comes
 * back. The backend remains the sole source of truth for who a token
 * belongs to and what role it has.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [operator, setOperator] = useState<Operator | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function validateStoredToken() {
      const token = getStoredToken();
      if (!token) {
        if (!cancelled) setStatus("unauthenticated");
        return;
      }
      try {
        const op = await fetchCurrentOperator();
        if (!cancelled) {
          setOperator(op);
          setStatus("authenticated");
        }
      } catch {
        if (!cancelled) {
          clearStoredToken();
          setOperator(null);
          setStatus("unauthenticated");
        }
      }
    }
    validateStoredToken();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (token: string): Promise<LoginResult> => {
    setStoredToken(token);
    try {
      const op = await fetchCurrentOperator();
      setOperator(op);
      setStatus("authenticated");
      return { ok: true };
    } catch (err) {
      clearStoredToken();
      setStatus("unauthenticated");
      return { ok: false, error: err instanceof Error ? err.message : "Invalid token." };
    }
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    setOperator(null);
    setStatus("unauthenticated");
  }, []);

  return (
    <AuthContext.Provider value={{ status, operator, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

type Permission = "read" | "execute" | "approve";

// Mirrors app/core/security.py::ROLE_PERMISSIONS exactly. This is a
// display-layer convenience only (hide a button someone can't use) -- the
// backend independently enforces every one of these checks server-side
// regardless of what the UI shows.
const ROLE_PERMISSIONS: Record<OperatorRole, ReadonlySet<Permission>> = {
  VIEWER: new Set(["read"]),
  OPERATOR: new Set(["read", "execute"]),
  APPROVER: new Set(["read", "approve"]),
  ADMIN: new Set(["read", "execute", "approve"]),
};

export function hasPermission(role: OperatorRole | undefined, permission: Permission): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.has(permission) ?? false;
}
