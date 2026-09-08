"use client";

import Link from "next/link";
import { Bot } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingBlock } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useAgents } from "@/hooks/use-safeops";

export default function AgentsPage() {
  const { data, isLoading, error } = useAgents();

  return (
    <div>
      <PageHeader title="Agents" description="Seeded agents and their permission profiles." />
      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={2} />}
      {data && (
        <div className="grid gap-4 sm:grid-cols-2">
          {data.map((agent) => (
            <Link key={agent.id} href={`/agents/${agent.id}`}>
              <Card className="h-full transition-colors hover:border-primary/40">
                <CardContent className="flex items-start gap-3">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
                    <Bot className="size-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-semibold">{agent.name}</p>
                      <Badge variant="secondary" className="capitalize">
                        {agent.type}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{agent.description}</p>
                    <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <span>Status: {agent.status}</span>
                      <span>·</span>
                      <span>Baseline risk: {agent.risk_level}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
