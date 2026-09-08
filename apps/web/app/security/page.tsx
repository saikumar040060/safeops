"use client";

import Link from "next/link";
import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ShieldAlert } from "lucide-react";

import { IncidentStatusBadge, RiskBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSecurityIncidents } from "@/hooks/use-safeops";
import type { RiskLevel } from "@/lib/types";

const SEVERITIES: Array<RiskLevel | "ALL"> = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function SecurityPage() {
  const [severity, setSeverity] = useState<RiskLevel | "ALL">("ALL");
  const { data, isLoading, error } = useSecurityIncidents(
    severity === "ALL" ? {} : { severity }
  );

  return (
    <div>
      <PageHeader
        title="Security Center"
        description="Every action the Risk Engine flagged, by severity."
      />

      <Tabs value={severity} onValueChange={(v) => setSeverity(v as RiskLevel | "ALL")}>
        <TabsList className="mb-4">
          {SEVERITIES.map((level) => (
            <TabsTrigger key={level} value={level}>
              {level === "ALL" ? "All" : level}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {error && <ErrorState error={error} />}
      {isLoading && <LoadingBlock rows={3} />}

      {data && data.length === 0 && (
        <EmptyState
          title="No security incidents"
          description="Launch the malicious ticket demo to see the Risk Engine in action."
        />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((incident) => (
            <Link key={incident.id} href={`/security/${incident.id}`}>
              <Card className="h-full transition-colors hover:border-primary/40">
                <CardContent className="flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <ShieldAlert className="size-4 text-muted-foreground" />
                      <span className="text-sm font-semibold">{incident.incident_type}</span>
                    </div>
                    <RiskBadge level={incident.severity} />
                  </div>
                  <p className="text-xs text-muted-foreground">{incident.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {incident.indicators.map((indicator) => (
                      <Badge key={indicator} variant="secondary" className="font-mono">
                        {indicator}
                      </Badge>
                    ))}
                  </div>
                  <div className="flex items-center justify-between">
                    <IncidentStatusBadge status={incident.status} />
                    <span className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
                    </span>
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
