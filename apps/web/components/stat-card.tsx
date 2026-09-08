import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: number | string;
  icon: LucideIcon;
  tone?: "default" | "warning" | "danger" | "success";
}) {
  const toneClasses: Record<string, string> = {
    default: "text-foreground",
    warning: "text-amber-600 dark:text-amber-400",
    danger: "text-red-600 dark:text-red-400",
    success: "text-emerald-600 dark:text-emerald-400",
  };

  return (
    <Card className="gap-2 py-4">
      <CardContent className="flex items-center justify-between px-4">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className={cn("mt-1 text-2xl font-semibold tabular-nums", toneClasses[tone])}>
            {value}
          </p>
        </div>
        <Icon className={cn("size-8 opacity-70", toneClasses[tone])} />
      </CardContent>
    </Card>
  );
}
