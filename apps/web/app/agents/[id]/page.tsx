import { AgentDetailView } from "./agent-detail-view";

export default async function AgentDetailPage(props: PageProps<"/agents/[id]">) {
  const { id } = await props.params;
  return <AgentDetailView agentId={id} />;
}
