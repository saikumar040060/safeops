import { AlertTriangle, Inbox, WifiOff } from "lucide-react";

import { ApiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-12 text-center">
      <Inbox className="size-6 text-muted-foreground" />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const isOffline = error instanceof ApiError && error.status === 0;
  const message =
    error instanceof Error ? error.message : "Something went wrong loading this data.";

  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-center">
      {isOffline ? (
        <WifiOff className="size-6 text-destructive" />
      ) : (
        <AlertTriangle className="size-6 text-destructive" />
      )}
      <p className="text-sm font-medium text-destructive">
        {isOffline ? "Backend unavailable" : "Failed to load"}
      </p>
      <p className="max-w-sm text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
