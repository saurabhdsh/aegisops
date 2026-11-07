import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Empty, ErrorNote } from "../components/ui";

type Asset = { id: string; name: string; external_id: string; environment: string; criticality: string };
type Point = { timestamp: string; value: number };
type Forecast = {
  entity_id: string;
  current_utilization: number;
  growth_per_hour: number | null;
  hours_to_exhaustion: number | null;
  sample_count: number;
  method: string;
  source: string;
  points?: Point[];
};
type Workflow = { id: string; kind: string; state: string; started_at: string | null; finished_at: string | null };
type Check = { name: string; passed: boolean };
type Prevented = {
  summary?: string;
  before_utilization?: number;
  utilization?: number;
  hours_to_exhaustion?: number;
  incident_avoided?: boolean;
  forecast_count?: number;
  alert_count?: number;
  current_utilization?: number;
  growth_per_hour?: number;
  configuration_item?: { name?: string };
  business_service?: { name?: string; criticality?: string };
};
type AgentBody = {
  items: { agent_name: string; summary: string; output?: Prevented }[];
  validation?: { status: string; summary: string; checks: Check[] } | null;
  change?: { number: string; state: string; summary: string } | null;
};

const WIDTH = 420;
const HEIGHT = 250;
const PAD = { l: 36, r: 16, t: 18, b: 28 };
const CLAIMS = "HOST-CLAIMS-DB-01";

function tone(value: number): string {
  if (value >= 90) return "var(--coral)";
  if (value >= 75) return "var(--amber)";
  return "var(--mint)";
}

function hoursLabel(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "steady";
  if (value >= 48) return `${(value / 24).toFixed(1)} d`;
  return `${value.toFixed(1)} h`;
}

function rateLabel(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}/h`;
}

function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(11, 16);
}

function byRisk(left: Forecast, right: Forecast): number {
  const leftHours = left.hours_to_exhaustion ?? Number.POSITIVE_INFINITY;
  const rightHours = right.hours_to_exhaustion ?? Number.POSITIVE_INFINITY;
  if (leftHours !== rightHours) return leftHours - rightHours;
  return right.current_utilization - left.current_utilization;
}

function minutesBetween(start: string | null, end: string | null): string {
  if (!start || !end) return "";
  const seconds = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes > 0 ? `${minutes}m ${rest}s` : `${rest}s`;
}

function smooth(coords: [number, number][]): string {
  if (!coords.length) return "";
  if (coords.length === 1) return `M${coords[0][0].toFixed(1)} ${coords[0][1].toFixed(1)}`;
  let path = `M${coords[0][0].toFixed(1)} ${coords[0][1].toFixed(1)}`;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const previous = coords[index - 1] || coords[index];
    const current = coords[index];
    const next = coords[index + 1];
    const after = coords[index + 2] || next;
    const c1x = current[0] + (next[0] - previous[0]) / 6;
    const c1y = current[1] + (next[1] - previous[1]) / 6;
    const c2x = next[0] - (after[0] - current[0]) / 6;
    const c2y = next[1] - (after[1] - current[1]) / 6;
    path += ` C${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${next[0].toFixed(1)} ${next[1].toFixed(1)}`;
  }
  return path;
}

function Ring({ value }: { value: number }) {
  const radius = 46;
  const length = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <svg viewBox="0 0 120 120" className="capacity-ring h-[88px] w-[88px] shrink-0" role="img" aria-label={`Disk ${clamped.toFixed(0)} percent full`}>
      <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(232,234,237,0.08)" strokeWidth="8" />
      <circle
        cx="60"
        cy="60"
        r={radius}
        fill="none"
        stroke={tone(clamped)}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${(clamped / 100) * length} ${length}`}
        transform="rotate(-90 60 60)"
      />
      <text x="60" y="58" textAnchor="middle" fill="#e7e8ea" fontSize="20" fontFamily="IBM Plex Mono, ui-monospace, monospace">
        {clamped.toFixed(0)}
      </text>
      <text x="60" y="74" textAnchor="middle" fill="#6a707a" fontSize="10">
        % full
      </text>
    </svg>
  );
}

function DiskChart({ forecast }: { forecast: Forecast }) {
  const measured = [...(forecast.points || [])]
    .filter((point) => Number.isFinite(point.value) && Number.isFinite(Date.parse(point.timestamp)))
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
  const rate = forecast.growth_per_hour;
  const hours = forecast.hours_to_exhaustion;
  const last = measured[measured.length - 1];
  const horizon = hours != null && hours > 0 && hours <= 36 ? hours : rate != null && rate > 0 ? 12 : 0;
  const projected = last && horizon > 0 && rate != null
    ? { timestamp: new Date(Date.parse(last.timestamp) + horizon * 3600000).toISOString(), value: Math.min(100, last.value + rate * horizon) }
    : null;
  const stamps = measured.map((point) => Date.parse(point.timestamp));
  if (projected) stamps.push(Date.parse(projected.timestamp));
  const min = stamps.length ? Math.min(...stamps) : 0;
  const max = stamps.length ? Math.max(...stamps) : 1;
  const span = max === min ? 1 : max - min;
  const innerW = WIDTH - PAD.l - PAD.r;
  const innerH = HEIGHT - PAD.t - PAD.b;
  const xOf = (iso: string) => PAD.l + ((Date.parse(iso) - min) / span) * innerW;
  const yOf = (value: number) => PAD.t + (1 - Math.max(0, Math.min(100, value)) / 100) * innerH;
  const coords = measured.map((point) => [xOf(point.timestamp), yOf(point.value)] as [number, number]);
  const curve = smooth(coords);
  const area = coords.length > 1
    ? `${curve} L${coords[coords.length - 1][0].toFixed(1)} ${(HEIGHT - PAD.b).toFixed(1)} L${coords[0][0].toFixed(1)} ${(HEIGHT - PAD.b).toFixed(1)} Z`
    : "";
  const ticks = [0, 25, 50, 75, 100];
  const reachesFull = projected != null && projected.value >= 99.5;

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label={`Disk utilization for ${forecast.entity_id}, last sample ${forecast.current_utilization}%`}>
      <defs>
        <linearGradient id="capacity-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7c5cff" stopOpacity="0.42" />
          <stop offset="70%" stopColor="#6fbfc9" stopOpacity="0.08" />
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
      <line x1={PAD.l} x2={WIDTH - PAD.r} y1={yOf(75)} y2={yOf(75)} stroke="#e2a33a" strokeDasharray="4 4" strokeOpacity="0.85" />
      <text x={WIDTH - PAD.r} y={yOf(75) - 6} textAnchor="end" fill="#e2a33a" fontSize="10">75%</text>
      {area ? <path d={area} fill="url(#capacity-fill)" /> : null}
      {curve ? (
        <path d={curve} fill="none" stroke="#7c5cff" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" pathLength={1} className="capacity-draw" />
      ) : null}
      {projected && last ? (
        <line
          x1={xOf(last.timestamp)}
          y1={yOf(last.value)}
          x2={xOf(projected.timestamp)}
          y2={yOf(projected.value)}
          stroke="#6fbfc9"
          strokeWidth="2"
          strokeDasharray="5 4"
          strokeLinecap="round"
        />
      ) : null}
      {measured.map((point) => (
        <circle key={point.timestamp} cx={xOf(point.timestamp)} cy={yOf(point.value)} r="3.4" fill="#0c0d10" stroke="#c5c8ce" strokeWidth="1.6" />
      ))}
      {last ? <circle cx={xOf(last.timestamp)} cy={yOf(last.value)} r="4.2" fill="#0c0d10" stroke={tone(last.value)} strokeWidth="2.4" /> : null}
      {measured.filter((_, index) => index === 0 || index === measured.length - 1).map((point) => (
        <text key={`label-${point.timestamp}`} x={xOf(point.timestamp)} y={HEIGHT - 8} textAnchor="middle" fill="#6a707a" fontSize="10" fontFamily="IBM Plex Mono, ui-monospace, monospace">
          {clock(point.timestamp)}
        </text>
      ))}
      {projected ? (
        <text x={xOf(projected.timestamp)} y={HEIGHT - 8} textAnchor="end" fill="#6fbfc9" fontSize="10" fontFamily="IBM Plex Mono, ui-monospace, monospace">
          {reachesFull ? "100%" : `+${horizon.toFixed(0)}h`}
        </text>
      ) : null}
    </svg>
  );
}

function Spark({ points }: { points: Point[] }) {
  const ordered = [...points].filter((point) => Number.isFinite(point.value)).sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
  if (ordered.length < 2) return <div className="h-7 w-[72px]" />;
  const width = 72;
  const height = 28;
  const coords = ordered.map((point, index) => {
    const x = (index / (ordered.length - 1)) * width;
    const y = height - (Math.max(0, Math.min(100, point.value)) / 100) * height;
    return [x, y] as [number, number];
  });
  const last = ordered[ordered.length - 1].value;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-7 w-[72px]" aria-hidden="true">
      <path d={smooth(coords)} fill="none" stroke={tone(last)} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function Capacity() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [risks, setRisks] = useState<Forecast[]>([]);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [detail, setDetail] = useState<AgentBody | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    Promise.all([
      api<Asset[]>("/api/v1/capacity/assets"),
      api<{ items: Forecast[] }>("/api/v1/capacity/forecasts"),
      api<{ items: Forecast[] }>("/api/v1/capacity/risks"),
      api<{ items: Workflow[] }>("/api/v1/workflows?limit=100"),
    ])
      .then(async ([assetRows, forecastBody, riskBody, workflows]) => {
        setAssets(assetRows);
        setForecasts(forecastBody.items);
        setRisks(riskBody.items);
        const preferred = forecastBody.items.find((item) => item.entity_id === CLAIMS) || [...forecastBody.items].sort(byRisk)[0];
        setSelectedId(preferred?.entity_id || "");
        const capacity = workflows.items.find((item) => item.kind === "capacity");
        setWorkflow(capacity || null);
        if (capacity) setDetail(await api<AgentBody>(`/api/v1/workflows/${capacity.id}/agents`));
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"))
      .finally(() => setReady(true));
  }, []);

  const ordered = useMemo(() => [...forecasts].sort(byRisk), [forecasts]);
  const selected = ordered.find((item) => item.entity_id === selectedId) || ordered[0];
  const claimsSelected = selected?.entity_id === CLAIMS;
  const capacityAgent = detail?.items.find((item) => item.agent_name === "capacity_risk");
  const correlation = detail?.items.find((item) => item.agent_name === "event_correlation");
  const validationAgent = detail?.items.find((item) => item.agent_name === "validation");
  const after = validationAgent?.output;
  const elapsed = workflow ? minutesBetween(workflow.started_at, workflow.finished_at) : "";
  const hostName = claimsSelected ? capacityAgent?.output?.configuration_item?.name || "claims-db-01" : selected?.entity_id || "No host";
  const serviceLine = claimsSelected
    ? `${capacityAgent?.output?.business_service?.name || "Claims"} · ${capacityAgent?.output?.business_service?.criticality || "tier-1"}`
    : selected ? `${selected.source} · ${selected.method} slope · ${selected.sample_count} samples` : "";

  return (
    <div className="capacity-page flex h-[calc(100dvh-6.25rem)] min-h-[420px] flex-col">
      <div className="shrink-0">
        <h1 className="text-2xl">Capacity</h1>
        <p className="mono mt-1 text-[11px] text-[var(--ink-faint)]">{risks.length} at risk · {forecasts.length} forecasts</p>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">Disk utilization, the measured slope, and the hours left before the volume fills.</p>
      </div>
      {error ? <div className="mt-4 shrink-0"><ErrorNote message={error} /></div> : null}
      {!ready ? <p className="mt-4 text-sm text-[var(--ink-muted)]">Loading capacity…</p> : !selected ? (
        <div className="mt-4"><Empty title="No disk forecast" detail="Forecasts appear when disk samples are stored, or when Dynatrace returns at least two points for a host." /></div>
      ) : (
        <div className="mt-4 min-h-0 w-full min-w-0 flex-1 space-y-4 overflow-auto">
          <section className="card p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-faint)]">Selected volume</div>
            <h2 className="mt-1 text-xl">{hostName}</h2>
            <p className="mt-0.5 text-sm text-[var(--ink-muted)]">{serviceLine}</p>
            {claimsSelected && workflow ? <div className="mt-2"><Badge value={workflow.state} /></div> : null}
            <div className="mt-3">
              <Meter value={selected.current_utilization} />
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Ring value={selected.current_utilization} />
              <p className="mono min-w-0 text-[12px] leading-5 text-[var(--ink-muted)]">
                <span className="text-[var(--ink)]">{rateLabel(selected.growth_per_hour)}</span>
                {" · "}
                <span className={(selected.hours_to_exhaustion ?? 99) <= 6 ? "text-[var(--amber)]" : "text-[var(--ink)]"}>{hoursLabel(selected.hours_to_exhaustion)} to full</span>
                {" · "}
                {selected.sample_count} samples
              </p>
            </div>
            <div className="mt-3">
              {selected.points && selected.points.length > 1 ? <DiskChart forecast={selected} /> : (
                <p className="py-8 text-center text-sm text-[var(--ink-muted)]">This forecast has fewer than two samples, so there is no curve to draw.</p>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--ink-muted)]">
              <span className="inline-flex items-center gap-1.5"><i className="inline-block h-0.5 w-4 rounded bg-[var(--violet)]" /> Measured</span>
              <span className="inline-flex items-center gap-1.5"><i className="inline-block h-0.5 w-4 rounded border-t border-dashed border-[var(--cyan)]" /> Linear projection</span>
              <span className="inline-flex items-center gap-1.5"><i className="inline-block h-0.5 w-4 rounded border-t border-dashed border-[var(--amber)]" /> 75% watch</span>
            </div>
            <p className="mt-2 text-[12px] text-[var(--ink-faint)]">
              The curve follows the samples. The dashed line continues the measured slope and is not another sample.
              {selected.hours_to_exhaustion != null && selected.hours_to_exhaustion > 36 ? ` Full exhaustion is ${hoursLabel(selected.hours_to_exhaustion)} out, past the window drawn here.` : ""}
            </p>
            {claimsSelected ? (
              <div className="mt-3 border-t border-[var(--line-soft)] pt-3 text-sm">
                <div className="text-[var(--ink-muted)]">{correlation?.summary || "The forecast event is grouped with the related disk alerts."}</div>
                {correlation?.output?.alert_count != null ? (
                  <div className="mt-1 tabular">{correlation.output.forecast_count ?? 1} forecast · {correlation.output.alert_count} alerts grouped into one event</div>
                ) : null}
                {after?.utilization != null ? (
                  <div className="mt-2">
                    <div className="tabular">{after.before_utilization ?? selected.current_utilization}% → <span className="text-[var(--mint)]">{after.utilization}%</span> after the certified cleanup and volume extension.</div>
                    <div className="mt-1 text-[var(--mint)]">{after.incident_avoided ? "No incident raised. Corrected before service impact." : "Prevention is not confirmed."}</div>
                    {elapsed ? <div className="mt-1 text-[var(--ink-muted)]">Prediction to remediation {elapsed}.</div> : null}
                    {detail?.change ? <div className="mt-1">Standard change {detail.change.number} · {detail.change.state}</div> : null}
                  </div>
                ) : (
                  <div className="mt-2 text-[var(--ink-muted)]">{workflow?.state === "AWAITING_APPROVAL" ? "Waiting on the DBA approval card." : "The before-and-after utilization appears after the runbook finishes."}</div>
                )}
                {workflow ? <Link to={`/workflows/${workflow.id}`} className="mt-2 inline-block text-[var(--violet)]">Open the capacity workflow</Link> : null}
              </div>
            ) : null}
          </section>
          <section>
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-faint)]">Hosts</h2>
            <div className="mt-2 flex min-w-0 gap-2 overflow-x-auto pb-1">
              {ordered.map((item) => {
                const active = item.entity_id === selected.entity_id;
                const risk = risks.some((risk) => risk.entity_id === item.entity_id);
                return (
                  <button
                    key={item.entity_id}
                    type="button"
                    onClick={() => setSelectedId(item.entity_id)}
                    className={`card flex w-[168px] shrink-0 items-center justify-between gap-2 px-3 py-2 text-left ${active ? "border-[var(--violet)]" : ""}`}
                    aria-pressed={active}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium">{item.entity_id === CLAIMS ? "claims-db-01" : item.entity_id}</span>
                      <span className={`mono mt-0.5 block text-[11px] ${risk ? "text-[var(--amber)]" : "text-[var(--ink-muted)]"}`}>
                        {item.current_utilization.toFixed(0)}% · {hoursLabel(item.hours_to_exhaustion)}
                      </span>
                    </span>
                    <Spark points={item.points || []} />
                  </button>
                );
              })}
            </div>
          </section>
          <p className="text-[12px] text-[var(--ink-faint)]">
            {assets.length} configuration items in this tenant. Topology has the service map.
          </p>
        </div>
      )}
    </div>
  );
}

function Meter({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="h-2.5 overflow-hidden rounded-full bg-[var(--bg)]" role="img" aria-label={`${clamped.toFixed(0)} percent of the volume is used`}>
      <div className="h-full rounded-full" style={{ width: `${clamped}%`, background: `linear-gradient(90deg, var(--cyan), ${tone(clamped)})` }} />
    </div>
  );
}
