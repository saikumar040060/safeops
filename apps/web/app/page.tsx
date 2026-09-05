"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/lib/api";

export default function Home() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: false,
  });

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">SafeOps</h1>
      <p className="text-sm text-muted-foreground">
        Milestone 1 — frontend/backend connectivity check
      </p>
      <div className="rounded-md border px-4 py-3 text-sm">
        {isLoading && <span>Checking backend…</span>}
        {error && (
          <span className="text-red-600">
            Backend unreachable: {(error as Error).message}
          </span>
        )}
        {data && (
          <span className="text-green-600">
            Backend status: {data.status}
          </span>
        )}
      </div>
    </main>
  );
}
