"use client";

import Link from "next/link";
import { useState } from "react";
import { format } from "date-fns";
import { ArrowLeft, ChevronDown, ChevronRight } from "lucide-react";

import { IncidentStatusBadge, RiskBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingBlock } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useExecutionTimeline, useSecurityIncident } from "@/hooks/use-safeops";

export function SecurityIncidentDetailView({ incidentId }: { incidentId: string }) {
  const { data: incident, isLoading, error } = useSecurityIncident(incidentId);
  const { data: timeline } = useExecutionTimeline(incident?.execution_id ?? "");
  const [showSources, setShowSources] = useState(false);

  const untrustedSources =
    timeline?.steps.flatMap((step) => {
      const sources = (step.input as { sources?: Array<{ type: string; trust: string; content: string }> })
        .sources;
      return (sources ?? []).filter((source) => source.trust === "UNTRUSTED");
    }) ?? [];

  return (
    <div>
      <Button variant="ghost" size="sm" className="mb-2" render={<Link href="/security" />}>
        <ArrowLeft className="size-3.5" />
        Security
      </Button>

      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={4} />}

      {incident && (
        <>
          <PageHeader
            title={incident.incident_type}
            description={incident.title}
            actions={
              <>
                <RiskBadge level={incident.severity} />
                <IncidentStatusBadge status={incident.status} />
              </>
            }
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Summary</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p className="text-sm text-muted-foreground">{incident.description}</p>
                <div>
                  <p className="mb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    Signals / indicators
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {incident.indicators.map((indicator) => (
                      <Badge key={indicator} variant="destructive" className="font-mono">
                        {indicator}
                      </Badge>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  Detected {format(new Date(incident.created_at), "PPpp")}
                </p>
                <Link
                  href={`/executions/${incident.execution_id}`}
                  className="text-sm font-medium text-primary underline-offset-2 hover:underline"
                >
                  View execution →
                </Link>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Untrusted source content</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-2 text-xs text-muted-foreground">
                  The content below came from an untrusted source (e.g. a support ticket) and was
                  never treated as a control instruction. Shown here only for forensic review.
                </p>
                {untrustedSources.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No untrusted source content recorded for this incident.
                  </p>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowSources((v) => !v)}
                  >
                    {showSources ? (
                      <ChevronDown className="size-3.5" />
                    ) : (
                      <ChevronRight className="size-3.5" />
                    )}
                    {showSources ? "Hide" : "Show"} source content ({untrustedSources.length})
                  </Button>
                )}
                {showSources && (
                  <div className="mt-3 flex flex-col gap-2">
                    {untrustedSources.map((source, i) => (
                      <div key={i} className="rounded-md border bg-muted/40 p-2">
                        <Badge variant="outline" className="mb-1 border-amber-500/30 text-amber-600 dark:text-amber-400">
                          UNTRUSTED · {source.type}
                        </Badge>
                        <p className="font-mono text-xs whitespace-pre-wrap">{source.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
