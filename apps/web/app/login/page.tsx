"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { usePublicConfig } from "@/hooks/use-safeops";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { status, login } = useAuth();
  const { data: config } = usePublicConfig();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [status, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setError(null);
    const result = await login(token.trim());
    setSubmitting(false);
    if (result.ok) {
      router.replace("/dashboard");
    } else {
      setError("That token was not accepted. Check it and try again.");
    }
  }

  return (
    <div className="flex min-h-svh w-full items-center justify-center bg-muted/20 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <ShieldCheck className="size-4" />
            </div>
            <CardTitle className="text-base">Sign in to SafeOps</CardTitle>
          </div>
          <CardDescription>
            Paste your operator API token. Nothing else identifies you here -- the backend is
            the only source of truth for who this token belongs to.
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="flex flex-col gap-3">
            <Input
              type="password"
              autoComplete="off"
              autoFocus
              placeholder="sfops_..."
              value={token}
              onChange={(e) => setToken(e.target.value)}
              aria-label="API token"
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            {config?.demo_mode && (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs text-muted-foreground">
                <p className="mb-1 font-medium text-amber-600 dark:text-amber-400">
                  Local demo mode — no production auth
                </p>
                <p>
                  Try <code className="font-mono">sfops_demo_admin_allaccess</code> for full
                  access, or <code className="font-mono">sfops_demo_viewer_readonly</code> for a
                  read-only view.
                </p>
              </div>
            )}
          </CardContent>
          <CardFooter>
            <Button type="submit" className="w-full" disabled={submitting || !token.trim()}>
              {submitting ? "Checking…" : "Sign in"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
