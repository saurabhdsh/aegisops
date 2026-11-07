import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Empty, ErrorNote } from "../components/ui";

type Workflow = {
  id: string;
  kind: string;
  state: string;
  execution_mode: string;
  summary: string;
  incident_id: string | null;
  started_at: string | null;
  finished_at: string | null;
};
type Incident = { id: string; external_number?: string; number?: string; title: string; priority: string; state: string; ci_name?: string; service_name?: string };
type QueueIncident = { id: string; number: string; title: string; priority: string; state: string; ci_name: string; service_name: string };
type SampleAnalysis = {
  number: string;
  title: string;
  state: string;
  priority: string;
  ci_name: string;
  service_name: string;
  entity_id: string;
  workflow_id: string | null;
  source?: string;
  signals?: RcaOutput["signals"];
  hypotheses: Hypothesis[];
  series: { cpu: Sample[]; memory: Sample[] };
  confidence_note: string;
};
type Sample = { timestamp?: string; value: number; unit?: string };
type Hypothesis = { rank?: number; cause: string; confidence: number; limitations: string[]; requires_human_review: boolean };
type Change = { number?: string; summary?: string; opened_at?: string };
type Similar = { number?: string; title?: string; resolution_summary?: string; similarity_reason?: string };
type LogLine = { timestamp?: string; message?: string };
type Trace = { trace_id?: string; service?: string; span?: string; duration_ms?: number; message?: string; timestamp?: string };
type Check = { name: string; passed: boolean };
type RcaOutput = {
  signals?: {
    memory_slope_per_hour?: number | null;
    cpu_slope_per_hour?: number | null;
    deployment_lag_hours?: number | null;
    error_rate?: number | null;
    heap_profile?: boolean;
  };
  logs?: LogLine[];
  traces?: Trace[];
  traces_error?: string;
  series?: { cpu?: { points?: Sample[] }; memory?: { points?: Sample[] } };
  narrative?: string;
  llm_error?: string;
  model?: string;
  token_input?: number;
  token_output?: number;
  confidence_note?: string;
};
type TriageOutput = {
  impacted_ci?: { name?: string; class?: string; environment?: string; criticality?: string };
  business_service?: { name?: string; criticality?: string };
  priority?: string;
  related_changes?: Change[];
  similar?: Similar[];
};
type ValidationOutput = {
  passed?: boolean;
  summary?: string;
  checks?: Check[];
  series?: { cpu?: { points?: Sample[] }; memory?: { points?: Sample[] } };
};
type Agent = { agent_name: string; status: string; summary: string; model: string; latency_ms?: number; output?: Record<string, unknown> };

const WIDTH = 640;
const HEIGHT = 268;
const PAD = { l: 42, r: 14, t: 16, b: 34 };

function clock(iso?: string): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(11, 16);
  return date.toISOString().slice(11, 16);
}

function points(series?: { points?: Sample[] }): Sample[] {
  return (series?.points || []).filter((item) => Number.isFinite(item.value));
}

function lastValue(samples: Sample[]): number | null {
  return samples.length ? samples[samples.length - 1].value : null;
}

function peak(samples: Sample[]): number | null {
  if (!samples.length) return null;
  return Math.max(...samples.map((item) => item.value));
}

function formatRate(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}/h`;
}

function percent(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

function SeriesChart({
  cpu,
  memory,
  recoveryAt,
}: {
  cpu: Sample[];
  memory: Sample[];
  recoveryAt?: string;
}) {
  const stamps = [...cpu, ...memory].map((item) => Date.parse(item.timestamp || "")).filter((item) => Number.isFinite(item));
  const min = stamps.length ? Math.min(...stamps) : 0;
  const max = stamps.length ? Math.max(...stamps) : 1;
  const span = max === min ? 1 : max - min;
  const innerW = WIDTH - PAD.l - PAD.r;
  const innerH = HEIGHT - PAD.t - PAD.b;
  const xOf = (iso?: string) => {
    const time = Date.parse(iso || "");
    if (!Number.isFinite(time)) return PAD.l;
    return PAD.l + ((time - min) / span) * innerW;
  };
  const yOf = (value: number) => PAD.t + (1 - Math.max(0, Math.min(100, value)) / 100) * innerH;
  const line = (samples: Sample[]) =>
    samples
      .filter((item) => item.timestamp)
      .map((item, index) => `${index === 0 ? "M" : "L"}${xOf(item.timestamp).toFixed(1)} ${yOf(item.value).toFixed(1)}`)
      .join(" ");
  const area = (samples: Sample[]) => {
    const drawn = samples.filter((item) => item.timestamp);
    if (drawn.length < 2) return "";
    const first = drawn[0];
    const last = drawn[drawn.length - 1];
    return `${line(drawn)} L${xOf(last.timestamp).toFixed(1)} ${yOf(0).toFixed(1)} L${xOf(first.timestamp).toFixed(1)} ${yOf(0).toFixed(1)} Z`;
  };
  const ticks = [0, 25, 50, 75, 100];
  const labels = [...cpu, ...memory]
    .map((item) => item.timestamp)
    .filter((item, index, all): item is string => Boolean(item) && all.indexOf(item) === index)
    .sort();

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="CPU and memory samples across the incident window">
      <defs>
        <linearGradient id="rca-cpu" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7c5cff" stopOpacity="0.38" />
          <stop offset="100%" stopColor="#7c5cff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="rca-mem" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6fbfc9" stopOpacity="0.32" />
          <stop offset="100%" stopColor="#6fbfc9" stopOpacity="0" />
        </linearGradient>
      </defs>
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={PAD.l} x2={WIDTH - PAD.r} y1={yOf(tick)} y2={yOf(tick)} stroke="rgba(232,234,237,0.08)" />
          <text x={PAD.l - 8} y={yOf(tick) + 3} textAnchor="end" fill="#6a707a" fontSize="10" fontFamily="IBM Plex Mono, ui-monospace, monospace">
            {tick}
          </text>
        </g>
      ))}
      <line x1={PAD.l} x2={WIDTH - PAD.r} y1={yOf(80)} y2={yOf(80)} stroke="#e2a33a" strokeDasharray="4 4" strokeOpacity="0.8" />
      <text x={WIDTH - PAD.r} y={yOf(80) - 6} textAnchor="end" fill="#e2a33a" fontSize="10">
        80%
      </text>
      {recoveryAt ? (
        <line x1={xOf(recoveryAt)} x2={xOf(recoveryAt)} y1={PAD.t} y2={HEIGHT - PAD.b} stroke="rgba(125,206,160,0.55)" strokeDasharray="3 3" />
      ) : null}
      <path d={area(memory)} fill="url(#rca-mem)" />
      <path d={area(cpu)} fill="url(#rca-cpu)" />
      <path d={line(memory)} fill="none" stroke="#6fbfc9" strokeWidth="2.25" strokeLinejoin="round" strokeLinecap="round" />
      <path d={line(cpu)} fill="none" stroke="#7c5cff" strokeWidth="2.25" strokeLinejoin="round" strokeLinecap="round" />
      {cpu.map((item) => (
        <circle key={`cpu-${item.timestamp}`} cx={xOf(item.timestamp)} cy={yOf(item.value)} r="3.2" fill="#0c0d10" stroke="#7c5cff" strokeWidth="2" />
      ))}
      {memory.map((item) => (
        <circle key={`mem-${item.timestamp}`} cx={xOf(item.timestamp)} cy={yOf(item.value)} r="3.2" fill="#0c0d10" stroke="#6fbfc9" strokeWidth="2" />
      ))}
      {labels.filter((iso, index) => index === 0 || index === labels.length - 1 || iso === recoveryAt).map((iso) => (
        <text key={iso} x={xOf(iso)} y={HEIGHT - 10} textAnchor="middle" fill="#6a707a" fontSize="10" fontFamily="IBM Plex Mono, ui-monospace, monospace">
          {clock(iso)}
        </text>
      ))}
    </svg>
  );
}

export function Rca() {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [queue, setQueue] = useState<QueueIncident[]>([]);
  const [links, setLinks] = useState<Record<string, Workflow>>({});
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [sample, setSample] = useState<SampleAnalysis | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    Promise.all([
      api<{ items: QueueIncident[] }>("/api/v1/incidents?limit=200"),
      api<{ items: Workflow[] }>("/api/v1/workflows?limit=100"),
    ])
      .then(([incidents, flows]) => {
        const next: Record<string, Workflow> = {};
        for (const item of flows.items) {
          if (item.kind === "incident" && item.incident_id && item.state !== "CANCELLED" && item.state !== "FAILED") {
            next[item.incident_id] = item;
          }
        }
        setQueue(incidents.items);
        setLinks(next);
        const preferred = incidents.items.find((item) => next[item.id]) || incidents.items[0];
        setSelectedId(preferred?.id || "");
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    const flow = links[selectedId];
    setError("");
    if (!flow) {
      api<SampleAnalysis>(`/api/v1/incidents/${selectedId}/analysis`)
        .then((body) => {
          setSample(body);
          setWorkflow(null);
          setAgents([]);
          setHypotheses(body.hypotheses || []);
          setIncident({
            id: selectedId,
            number: body.number,
            title: body.title,
            priority: body.priority,
            state: body.state,
            ci_name: body.ci_name,
            service_name: body.service_name,
          });
        })
        .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
      return;
    }
    Promise.all([
      api<{ items: Agent[] }>(`/api/v1/workflows/${flow.id}/agents`),
      api<{ items: Hypothesis[] }>(`/api/v1/workflows/${flow.id}/hypotheses`),
      api<Incident>(`/api/v1/incidents/${selectedId}`),
    ])
      .then(([agentBody, hypothesisBody, record]) => {
        setSample(null);
        setWorkflow(flow);
        setAgents(agentBody.items);
        setHypotheses(hypothesisBody.items);
        setIncident(record);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, [selectedId, links]);

  const filtered = queue.filter((item) => `${item.number} ${item.title} ${item.service_name} ${item.ci_name}`.toLowerCase().includes(query.trim().toLowerCase()));
  const ordered = [...filtered].sort((left, right) => Number(Boolean(links[right.id])) - Number(Boolean(links[left.id])));

  if (!ready) return <p className="text-sm text-[var(--ink-muted)]">Loading root cause analysis…</p>;

  if (error && !incident) return <ErrorNote message={error} />;

  const rca = agents.find((item) => item.agent_name === "rca");
  const triage = agents.find((item) => item.agent_name === "triage");
  const validation = agents.find((item) => item.agent_name === "validation");
  const rcaOut = (sample
    ? {
        signals: sample.signals,
        series: { cpu: { points: sample.series.cpu }, memory: { points: sample.series.memory } },
        confidence_note: sample.confidence_note,
        logs: [],
        traces: [],
      }
    : (rca?.output || {})) as RcaOutput;
  const triageOut = (sample
    ? {
        impacted_ci: { name: sample.ci_name || incident?.ci_name },
        business_service: { name: sample.service_name || incident?.service_name },
        related_changes: [],
        similar: [],
      }
    : (triage?.output || {})) as TriageOutput;
  const validationOut = (validation?.output || {}) as ValidationOutput;
  const beforeCpu = points(rcaOut.series?.cpu);
  const beforeMemory = points(rcaOut.series?.memory);
  const afterCpu = points(validationOut.series?.cpu);
  const afterMemory = points(validationOut.series?.memory);
  const cpu = [...beforeCpu, ...afterCpu];
  const memory = [...beforeMemory, ...afterMemory];
  const signals = rcaOut.signals || {};
  const modelCalled = Boolean(rcaOut.model && rcaOut.model !== "deterministic-ranker");
  const fixture = workflow?.execution_mode === "SIMULATOR";
  const number = incident?.external_number || incident?.number || sample?.number || "";

  return (
    <div className="mx-auto max-w-5xl">
      <section className="card p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[15px] font-semibold">Incidents</h2>
          <div className="text-[12px] text-[var(--ink-muted)]">{queue.length} on the board · {Object.keys(links).length} investigated</div>
        </div>
        <input
          className="mt-3 w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm"
          placeholder="Search number, service, or host"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="mt-3 max-h-44 space-y-1 overflow-auto">
          {ordered.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSelectedId(item.id)}
              className={`flex w-full items-baseline justify-between gap-3 rounded-lg px-2 py-1.5 text-left text-sm ${item.id === selectedId ? "bg-[var(--bg-muted)]" : "hover:bg-[var(--bg-muted)]/60"}`}
            >
              <span className="min-w-0">
                <span className="mono text-[12px] text-[var(--titanium)]">{item.number}</span>
                <span className="ml-2">{item.title}</span>
              </span>
              <span className="shrink-0 text-[11px] text-[var(--ink-faint)]">{links[item.id] ? "investigated" : item.service_name}</span>
            </button>
          ))}
        </div>
      </section>

      {!incident ? <p className="mt-4 text-sm text-[var(--ink-muted)]">{error || "Select an incident."}</p> : <>
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}
      <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--ink-faint)]">Root cause analysis</div>
          <h1 className="mt-1 text-2xl">{incident?.title || sample?.title || workflow?.summary}</h1>
          <p className="mt-1 text-sm text-[var(--ink-muted)]">
            {number}
            {triageOut.business_service?.name ? ` · ${triageOut.business_service.name}` : ""}
            {triageOut.impacted_ci?.name ? ` · ${triageOut.impacted_ci.name}` : ""}
            {triageOut.impacted_ci?.criticality ? ` · ${triageOut.impacted_ci.criticality}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge value={workflow?.state || incident.state} />
          {workflow ? <Link to={`/workflows/${workflow.id}`} className="text-[13px] text-[var(--violet)] hover:underline">Workflow</Link> : null}
        </div>
      </div>

      <section className="card mt-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[15px] font-semibold">Utilization</h2>
          <div className="flex items-center gap-3 text-[12px] text-[var(--ink-muted)]">
            <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full bg-[var(--violet)]" /> CPU</span>
            <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2 w-2 rounded-full bg-[var(--cyan)]" /> Memory</span>
            <span className="inline-flex items-center gap-1.5"><span className="inline-block h-0.5 w-3 bg-[var(--amber)]" /> 80%</span>
          </div>
        </div>
        <div className="mt-2">
          {cpu.length || memory.length ? <SeriesChart cpu={cpu} memory={memory} recoveryAt={afterCpu[0]?.timestamp} /> : <Empty title="No samples" detail="The RCA agent stores a series only after Dynatrace returns points." />}
        </div>
        <p className="mt-1 text-[12px] text-[var(--ink-muted)]">
          {sample?.source === "dynatrace" ? "These points were just read from Dynatrace for this host." : sample ? "These points are the Dynatrace samples stored for this host. No investigation has run, so there is no recovery series." : `${fixture ? "These points are the Claims fixture stored on this simulator run." : "These points are the samples stored from the connector on this run."} The mint marker is the first validation sample after the runbook.`} The chart plots each stored sample.
        </p>
      </section>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Peak CPU" value={percent(peak(beforeCpu))} detail={afterCpu.length ? `recovered ${percent(lastValue(afterCpu))}` : "no recovery run"} tone="violet" />
        <Stat label="Peak memory" value={percent(peak(beforeMemory))} detail={afterMemory.length ? `recovered ${percent(lastValue(afterMemory))}` : "no recovery run"} tone="cyan" />
        <Stat label="CPU slope" value={formatRate(signals.cpu_slope_per_hour)} detail="measured across the saturation window" />
        <Stat label="Memory slope" value={formatRate(signals.memory_slope_per_hour)} detail={`error rate ${signals.error_rate == null ? "—" : `${(signals.error_rate * 100).toFixed(1)}%`}`} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <section className="card p-4">
          <h2 className="text-[15px] font-semibold">Ranked causes</h2>
          <p className="mt-1 text-[12px] text-[var(--ink-muted)]">{rcaOut.confidence_note || "Scores come from measured slopes and are not calibrated probabilities."}</p>
          {hypotheses.length === 0 ? <div className="mt-4"><Empty title="No hypotheses" detail="The ranker emits a cause only when a measured signal crosses its threshold." /></div> : (
            <ol className="mt-4 space-y-4">
              {hypotheses.map((item, index) => (
                <li key={`${item.rank || index}-${item.cause}`}>
                  <div className="flex items-baseline justify-between gap-3">
                    <div className="text-sm">{item.rank || index + 1}. {item.cause}</div>
                    <div className="mono shrink-0 text-[12px] text-[var(--ink)]">{item.confidence.toFixed(2)}</div>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--bg-muted)]">
                    <div className="h-full rounded-full bg-[var(--violet)]" style={{ width: `${Math.max(4, Math.min(100, item.confidence * 100))}%` }} />
                  </div>
                  {item.limitations?.length ? <div className="mt-1 text-[12px] text-[var(--ink-faint)]">{item.limitations.join(" · ")}</div> : null}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="card p-4">
          <h2 className="text-[15px] font-semibold">Model</h2>
          {modelCalled && rcaOut.narrative ? (
            <>
              <p className="mt-3 text-sm">{rcaOut.narrative}</p>
              <p className="mono mt-3 text-[11px] text-[var(--ink-muted)]">{rcaOut.model} · {rcaOut.token_input || 0} in · {rcaOut.token_output || 0} out</p>
            </>
          ) : (
            <p className="mt-3 text-sm text-[var(--ink-muted)]">{sample ? "The ranker read the stored samples. A model is called only when an investigation runs and a model is saved. It cannot add a cause or approve a runbook." : "This run used the deterministic ranker. A saved OpenAI or Azure OpenAI model restates these causes on the next investigation. It cannot add a cause or approve the runbook."}</p>
          )}
          {rcaOut.llm_error ? <div className="mt-3"><ErrorNote message={rcaOut.llm_error} /></div> : null}
          <dl className="mt-4 space-y-2 text-sm">
            <Row label="Deployment lag" value={signals.deployment_lag_hours == null ? "—" : `${signals.deployment_lag_hours.toFixed(1)} h`} />
            <Row label="Heap profile" value={signals.heap_profile ? "present" : "not in the evidence"} />
            <Row label="RCA latency" value={rca?.latency_ms != null ? `${rca.latency_ms} ms` : "—"} />
            <Row label="Source" value={sample ? `${sample.source || "stored-samples"} · ${sample.entity_id}` : workflow?.execution_mode || "—"} />
          </dl>
        </section>
      </div>

      {sample ? null : <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="card p-4">
          <h2 className="text-[15px] font-semibold">Change and evidence</h2>
          <ul className="mt-3 space-y-3 text-sm">
            {(triageOut.related_changes || []).map((item) => (
              <li key={item.number}>
                <div className="mono text-[12px] text-[var(--amber)]">{item.number} · {clock(item.opened_at)} UTC</div>
                <div className="mt-0.5">{item.summary}</div>
              </li>
            ))}
            {(rcaOut.logs || []).map((item) => (
              <li key={`${item.timestamp}-${item.message}`}>
                <div className="mono text-[12px] text-[var(--cyan)]">{clock(item.timestamp)} UTC · log</div>
                <div className="mt-0.5">{item.message}</div>
              </li>
            ))}
            {(rcaOut.traces || []).map((item) => (
              <li key={item.trace_id}>
                <div className="mono text-[12px] text-[var(--violet)]">{item.trace_id} · {item.duration_ms} ms</div>
                <div className="mt-0.5">{item.service} {item.span}</div>
                <div className="text-[var(--ink-muted)]">{item.message}</div>
              </li>
            ))}
          </ul>
          {rcaOut.traces_error ? <p className="mt-3 text-sm text-[var(--coral)]">{rcaOut.traces_error}</p> : null}
          {!rcaOut.traces_error && !(rcaOut.traces || []).length ? <p className="mt-3 text-[12px] text-[var(--ink-muted)]">No trace was stored on this run.</p> : null}
        </section>

        <section className="card p-4">
          <h2 className="text-[15px] font-semibold">Similar incidents</h2>
          <ul className="mt-3 space-y-3">
            {(triageOut.similar || []).map((item) => (
              <li key={item.number} className="border-b border-[var(--line-soft)] pb-3 last:border-0 last:pb-0">
                <div className="mono text-[12px] text-[var(--titanium)]">{item.number}</div>
                <div className="text-sm">{item.title}</div>
                <div className="text-[13px] text-[var(--ink-muted)]">{item.resolution_summary}</div>
              </li>
            ))}
          </ul>
          {(triageOut.similar || []).length === 0 ? <p className="mt-3 text-sm text-[var(--ink-muted)]">No similar incidents were returned.</p> : null}
        </section>
      </div>}

      {validationOut.checks?.length ? <section className="card mt-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[15px] font-semibold">Validation</h2>
          <Badge value={validationOut.passed ? "passed" : "pending"} />
        </div>
        <p className="mt-2 text-sm text-[var(--ink-muted)]">{validationOut.summary || "Validation is recorded after the runbook finishes."}</p>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {(validationOut.checks || []).map((item) => (
            <li key={item.name} className="flex items-center justify-between rounded-xl border border-[var(--line)] px-3 py-2 text-sm">
              <span>{item.name.replaceAll("_", " ")}</span>
              <span className={item.passed ? "text-[var(--mint)]" : "text-[var(--coral)]"}>{item.passed ? "passed" : "failed"}</span>
            </li>
          ))}
        </ul>
      </section> : null}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-[var(--ink-faint)]">
            <tr>
              <th className="py-2 font-medium">Time UTC</th>
              <th className="py-2 font-medium">Phase</th>
              <th className="py-2 font-medium">CPU</th>
              <th className="py-2 font-medium">Memory</th>
            </tr>
          </thead>
          <tbody>
            {mergedRows(beforeCpu, beforeMemory, sample ? "sample" : "saturation").concat(mergedRows(afterCpu, afterMemory, "recovery")).map((row) => (
              <tr key={`${row.phase}-${row.time}`} className="border-t border-[var(--line-soft)]">
                <td className="mono py-2 text-[12px]">{clock(row.time)}</td>
                <td className="py-2 text-[var(--ink-muted)]">{row.phase}</td>
                <td className="mono py-2">{row.cpu == null ? "—" : `${row.cpu}%`}</td>
                <td className="mono py-2">{row.memory == null ? "—" : `${row.memory}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </>}
    </div>
  );
}

function mergedRows(cpu: Sample[], memory: Sample[], phase: string) {
  const times = [...cpu, ...memory].map((item) => item.timestamp || "").filter(Boolean);
  return [...new Set(times)].sort().map((time) => ({
    time,
    phase,
    cpu: cpu.find((item) => item.timestamp === time)?.value ?? null,
    memory: memory.find((item) => item.timestamp === time)?.value ?? null,
  }));
}

function Stat({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: "violet" | "cyan" }) {
  const color = tone === "violet" ? "text-[var(--violet)]" : tone === "cyan" ? "text-[var(--cyan)]" : "text-[var(--ink)]";
  return (
    <div className="card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-[var(--ink-faint)]">{label}</div>
      <div className={`tabular mt-1 text-[26px] font-semibold leading-none ${color}`}>{value}</div>
      <div className="mt-2 text-[12px] text-[var(--ink-muted)]">{detail}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[var(--ink-muted)]">{label}</dt>
      <dd className="mono text-[12px]">{value}</dd>
    </div>
  );
}
