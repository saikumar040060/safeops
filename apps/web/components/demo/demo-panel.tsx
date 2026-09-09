"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, PlayCircle } from "lucide-react";
import { toast } from "sonner";

import { fetchAgents } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useStartExecution } from "@/hooks/use-safeops";
import { hasPermission, useAuth } from "@/lib/auth";

type Demo = {
  id: string;
  label: string;
  agentName: "support-agent" | "devops-agent";
  objective: string;
  description: string;
};

const DEMOS: Demo[] = [
  {
    id: "refund",
    label: "A. Duplicate refund",
    agentName: "support-agent",
    objective: "Investigate duplicate payment for CUST-1001 and refund the duplicate",
    description: "read_customer → get_payments → refund_payment → approval → completed",
  },
  {
    id: "attack",
    label: "B. Malicious ticket",
    agentName: "support-agent",
    objective: "Investigate support ticket TCK-4837",
    description: "Prompt injection attempt — Risk Engine should BLOCK before any side effect",
  },
  {
    id: "staging",
    label: "C. Staging deploy",
    agentName: "devops-agent",
    objective: "Deploy checkout-service version 2.0 to staging",
    description: "get_deployment → deploy_staging → completed, no approval required",
  },
  {
    id: "production",
    label: "D. Production deploy",
    agentName: "devops-agent",
    objective: "Deploy checkout-service version 2.0 to production",
    description: "deploy_production requires approval before it executes",
  },
];

export function DemoPanel() {
  const router = useRouter();
  const startExecution = useStartExecution();
  const [launchingId, setLaunchingId] = useState<string | null>(null);
  const { operator } = useAuth();
  const canLaunch = hasPermission(operator?.role, "execute");

  async function launch(demo: Demo) {
    setLaunchingId(demo.id);
    try {
      const agents = await fetchAgents();
      const agent = agents.find((a) => a.name === demo.agentName);
      if (!agent) {
        toast.error(`Seeded agent "${demo.agentName}" not found.`);
        return;
      }
      const result = await startExecution.mutateAsync({
        agent_id: agent.id,
        objective: demo.objective,
      });
      if (!result.execution_id) {
        toast.error(result.reason ?? "Could not start the demo execution.");
        return;
      }
      toast.success(`Launched: ${demo.label}`);
      router.push(`/executions/${result.execution_id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to launch demo.");
    } finally {
      setLaunchingId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Demo workflows</CardTitle>
        <CardDescription>
          Launches a real execution against the live backend. Nothing here is simulated.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        {DEMOS.map((demo) => (
          <div
            key={demo.id}
            className="flex flex-col justify-between gap-3 rounded-lg border bg-card p-3"
          >
            <div>
              <p className="text-sm font-medium">{demo.label}</p>
              <p className="mt-1 text-xs text-muted-foreground">{demo.description}</p>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="self-start"
              disabled={launchingId !== null || !canLaunch}
              title={canLaunch ? undefined : "Your role cannot start executions."}
              onClick={() => launch(demo)}
            >
              {launchingId === demo.id ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <PlayCircle className="size-3.5" />
              )}
              Launch
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
