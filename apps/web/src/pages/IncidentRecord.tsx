import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, ErrorNote } from "../components/ui";

type Incident = {
  id: string;
  number: string;
  title: string;
  description: string;
  state: string;
  source_state: string;
  priority: string;
  ci_name: string;
  service_name: string;
  opened_at: string | null;
  resolved_at: string | null;
  work_notes: string[];
};
type Evidence = { id: string; kind: string; summary: string; source: string; content_hash: string };
type Workflow = { id: string; kind: string; state: string; incident_id: string | null };

export function IncidentRecord() {
  const { incidentId = "" } = useParams();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [workflowId, setWorkflowId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<Incident>(`/api/v1/incidents/${incidentId}`),
      api<Evidence[]>(`/api/v1/incidents/${incidentId}/evidence`),
      api<{ items: Workflow[] }>("/api/v1/workflows"),
    ])
      .then(([record, attached, workflows]) => {
        setIncident(record);
        setEvidence(attached);
        setWorkflowId(workflows.items.find((item) => item.incident_id === incidentId)?.id || "");
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, [incidentId]);

  if (!incident) return error ? <ErrorNote message={error} /> : <p className="text-sm text-[var(--ink-muted)]">Loading incident…</p>;

  return (
    <div className="max-w-3xl">
      <div className="mono text-[11px] text-[var(--ink-muted)]">ServiceNow · {incident.number}</div>
      <div className="mt-1 flex items-start justify-between gap-4">
        <h1 className="text-2xl">{incident.title}</h1>
        <Badge value={incident.state} />
      </div>
      <p className="mt-3 text-sm text-[var(--ink-muted)]">{incident.description}</p>
      <dl className="card mt-6 grid gap-3 p-4 text-sm sm:grid-cols-2">
        <div><dt className="text-[var(--ink-muted)]">Priority</dt><dd>P{incident.priority}</dd></div>
        <div><dt className="text-[var(--ink-muted)]">Source state</dt><dd>{incident.source_state || "—"}</dd></div>
        <div><dt className="text-[var(--ink-muted)]">Configuration item</dt><dd>{incident.ci_name || "—"}</dd></div>
        <div><dt className="text-[var(--ink-muted)]">Business service</dt><dd>{incident.service_name || "—"}</dd></div>
        <div><dt className="text-[var(--ink-muted)]">Opened</dt><dd className="mono text-[12px]">{incident.opened_at || "—"}</dd></div>
        <div><dt className="text-[var(--ink-muted)]">Resolved</dt><dd className="mono text-[12px]">{incident.resolved_at || "—"}</dd></div>
      </dl>
      {workflowId ? <Link className="mt-4 inline-block text-sm text-[var(--violet)]" to={`/workflows/${workflowId}`}>Open the agent workflow</Link> : null}
      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Work notes</h2>
        <ul className="mt-3 space-y-2">
          {incident.work_notes.map((note) => (
            <li key={note} className="card px-4 py-3 text-sm">{note}</li>
          ))}
        </ul>
      </section>
      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Attached evidence</h2>
        {evidence.length === 0 ? <p className="mt-3 text-sm text-[var(--ink-muted)]">No evidence is attached yet.</p> : (
          <ul className="mt-3 space-y-2">
            {evidence.map((item) => (
              <li key={item.id} className="card px-4 py-3 text-sm">
                <div>{item.kind} · {item.summary}</div>
                <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]">{item.source} · {item.content_hash.slice(0, 12)}</div>
              </li>
            ))}
          </ul>
        )}
      </section>
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}
    </div>
  );
}
