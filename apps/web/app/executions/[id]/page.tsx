import { ExecutionDetailView } from "./execution-detail-view";

export default async function ExecutionDetailPage(props: PageProps<"/executions/[id]">) {
  const { id } = await props.params;
  return <ExecutionDetailView executionId={id} />;
}
