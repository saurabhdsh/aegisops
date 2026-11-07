import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Empty, ErrorNote } from "../components/ui";

type Incident = {
  id: string;
  number: string;
  title: string;
  state: string;
  priority: string;
  service_name: string;
  ci_name: string;
  opened_at: string | null;
};
type Workflow = { id: string; kind: string; state: string; incident_id: string | null };

const PRIORITIES = ["1", "2", "3", "4"] as const;

function openedLabel(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function Incidents() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [priority, setPriority] = useState("");
  const [state, setState] = useState("");

  useEffect(() => {
    Promise.all([
      api<{ items: Incident[] }>("/api/v1/incidents?limit=100"),
      api<{ items: Workflow[] }>("/api/v1/workflows?limit=100"),
    ])
      .then(([incidentPage, workflowPage]) => {
        setIncidents(incidentPage.items);
        setWorkflows(workflowPage.items);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, []);

  const byIncident = useMemo(() => {
    const map = new Map<string, Workflow>();
    for (const workflow of workflows) {
      if (workflow.incident_id) map.set(workflow.incident_id, workflow);
    }
    return map;
  }, [workflows]);

  const states = useMemo(() => [...new Set(incidents.map((item) => item.state).filter(Boolean))], [incidents]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return incidents.filter((item) => {
      if (priority && item.priority !== priority) return false;
      if (state && item.state !== state) return false;
      if (!needle) return true;
      return [item.number, item.title, item.service_name, item.ci_name].join(" ").toLowerCase().includes(needle);
    });
  }, [incidents, priority, query, state]);

  const counts = {
    p1: incidents.filter((item) => item.priority === "1").length,
    p2: incidents.filter((item) => item.priority === "2").length,
    open: incidents.filter((item) => item.state === "open" || item.state === "in_progress").length,
    agents: workflows.length,
  };

  return (
    <div className="flex h-[calc(100dvh-6.25rem)] min-h-[420px] flex-col">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl">Incidents</h1>
          <p className="mt-1 text-sm text-[var(--ink-muted)]">
            {counts.open} active · {counts.p1} P1 · {counts.p2} P2 · {counts.agents} agent workflows
          </p>
        </div>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search number, service, host"
          className="w-full max-w-xs rounded-lg border border-[var(--line)] bg-[var(--bg-elev)] px-3 py-2 text-[13px] outline-none focus:border-[var(--violet)]"
        />
      </div>

      <div className="mt-3 flex shrink-0 flex-wrap gap-1.5">
        <FilterChip active={priority === ""} onClick={() => setPriority("")}>All</FilterChip>
        {PRIORITIES.map((item) => (
          <FilterChip key={item} active={priority === item} onClick={() => setPriority(priority === item ? "" : item)}>
            P{item}
          </FilterChip>
        ))}
        <span className="mx-1 w-px bg-[var(--line)]" />
        <FilterChip active={state === ""} onClick={() => setState("")}>Any state</FilterChip>
        {states.map((item) => (
          <FilterChip key={item} active={state === item} onClick={() => setState(state === item ? "" : item)}>
            {item.replaceAll("_", " ")}
          </FilterChip>
        ))}
      </div>

      {error ? <div className="mt-3 shrink-0"><ErrorNote message={error} /></div> : null}

      <div className="card mt-3 min-h-0 flex-1 overflow-auto">
        {incidents.length === 0 ? (
          <div className="p-6"><Empty title="No incidents" detail="ServiceNow records appear here as they are ingested." /></div>
        ) : visible.length === 0 ? (
          <p className="p-6 text-sm text-[var(--ink-muted)]">No incidents match this filter.</p>
        ) : (
          <ul>
            {visible.map((item) => {
              const workflow = byIncident.get(item.id);
              return (
                <li key={item.id} className="border-b border-[var(--line)] px-3 py-2 last:border-0 hover:bg-[var(--bg-muted)]">
                  <div className="flex items-center gap-2">
                    <Link to={`/incidents/${item.id}`} className="mono shrink-0 text-[12px] text-[var(--titanium)] hover:text-[var(--ink)]">{item.number || item.id}</Link>
                    <span className={`text-[12px] font-semibold ${item.priority === "1" ? "text-[var(--coral)]" : item.priority === "2" ? "text-[var(--amber)]" : "text-[var(--ink-muted)]"}`}>P{item.priority || "—"}</span>
                    <span className="ml-auto"><Badge value={item.state || "unknown"} /></span>
                  </div>
                  <Link to={`/incidents/${item.id}`} className="mt-0.5 block truncate text-[13px] hover:text-[var(--violet)]">{item.title}</Link>
                  <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[11px] text-[var(--ink-muted)]">
                    <span className="truncate">{item.service_name || "Unassigned"} · {item.ci_name || "no host"} · {openedLabel(item.opened_at)}</span>
                    {workflow ? <Link to={`/workflows/${workflow.id}`} className="shrink-0 text-[var(--violet)] hover:underline">{workflow.state.replaceAll("_", " ")}</Link> : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <p className="mt-2 shrink-0 text-[12px] text-[var(--ink-faint)]">{visible.length} of {incidents.length} shown</p>
    </div>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-2.5 py-1 text-[12px] font-medium ${active ? "bg-[var(--violet)] text-white" : "bg-[var(--bg-elev)] text-[var(--ink-muted)] hover:text-[var(--ink)]"}`}
    >
      {children}
    </button>
  );
}
