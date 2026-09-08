import { redactEntries, redactedLabel, truncate } from "@/lib/redact";

export function RedactedFields({
  data,
  emptyLabel = "No arguments",
}: {
  data: Record<string, unknown> | null | undefined;
  emptyLabel?: string;
}) {
  const entries = redactEntries(data);
  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-xs">
      {entries.map(({ key, value, redacted }) => (
        <div key={key} className="contents">
          <dt className="font-mono text-muted-foreground">{key}</dt>
          <dd
            className={redacted ? "font-mono tracking-widest text-muted-foreground" : "font-mono"}
          >
            {redacted ? redactedLabel() : truncate(value, 200)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
