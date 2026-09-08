import { SecurityIncidentDetailView } from "./security-incident-detail-view";

export default async function SecurityIncidentDetailPage(
  props: PageProps<"/security/[id]">
) {
  const { id } = await props.params;
  return <SecurityIncidentDetailView incidentId={id} />;
}
