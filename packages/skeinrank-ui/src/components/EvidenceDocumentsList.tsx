import type { ElasticsearchEvidenceDocument } from "../types";

export function EvidenceDocumentsList({
  documents,
  emptyMessage = "No evidence snippets found.",
}: {
  documents: ElasticsearchEvidenceDocument[];
  emptyMessage?: string;
}) {
  if (documents.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        {emptyMessage}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((document) => (
        <div
          className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-950"
          key={`${document.index_name}:${document.document_id}:${document.field}:${document.match_start}`}
        >
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {document.index_name} / {document.document_id} / {document.field}
          </div>
          <EvidenceFragment document={document} />
        </div>
      ))}
    </div>
  );
}

function EvidenceFragment({
  document,
}: {
  document: ElasticsearchEvidenceDocument;
}) {
  const start = Math.max(
    0,
    Math.min(document.fragment.length, document.match_start),
  );
  const end = Math.max(
    start,
    Math.min(document.fragment.length, document.match_end),
  );

  return (
    <p className="leading-6 text-slate-700 dark:text-slate-200">
      {document.fragment.slice(0, start)}
      <mark className="rounded bg-amber-200 px-1 text-slate-950 dark:bg-amber-400/80">
        {document.fragment.slice(start, end) || document.matched_text}
      </mark>
      {document.fragment.slice(end)}
    </p>
  );
}
