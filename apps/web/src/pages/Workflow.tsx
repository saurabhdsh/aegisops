import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Button, Empty, ErrorNote } from "../components/ui";

type WorkflowBody = {
  id: string;
  kind: string;
  state: string;
  execution_mode: string;
  autonomy_level: string;
  summary: string;
  incident_id: string | null;
  started_at: string | null;
  finished_at: string | null;
};
type Hypothesis = { rank: number; cause: string; confidence: number; limitations: string[]; requires_human_review: boolean };
type Plan = { summary: string; parameters: Record<string, string>; risk_level: string; rollback_available: boolean; plan_hash: string } | null;
type Agent = {
  agent_name: string;
  status: string;
  summary: string;
  model: string;
  latency_ms?: number;
  output?: Record<string, unknown>;
};
type Tool = { tool_name: string; status: string };
type Execution = { status: string; phase: string; external_execution_id: string; result: { executor?: string; log?: string[]; deleted_bytes?: number } };
type Approval = { id: string; workflow_id: string; status: string; required_role: string };
type Check = { name: string; passed: boolean };
type Notice = { channel: string; recipient: string; subject: string; body: string; status: string };
type ChangeRow = { number: string; state: string; summary: string };
type AgentBody = { items: Agent[]; tools: Tool[]; validation?: { status: string; summary: string; checks: Check[] } | null; notifications?: Notice[]; change?: ChangeRow | null };

function elapsed(start: string | null, end: string | null): string {
  if (!start || !end) return "";
  const seconds = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes > 0 ? `${minutes}m ${rest}s` : `${rest}s`;
}

export function Workflow() {
  const { workflowId = "" } = useParams();
  const [workflow, setWorkflow] = useState<WorkflowBody | null>(null);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [plan, setPlan] = useState<Plan>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [validation, setValidation] = useState<AgentBody["validation"]>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [change, setChange] = useState<ChangeRow | null>(null);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");

  async function load() {
    const [item, hypothesisBody, planBody, agentBody, executionBody, approvals] = await Promise.all([
      api<WorkflowBody>(`/api/v1/workflows/${workflowId}`),
      api<{ items: Hypothesis[] }>(`/api/v1/workflows/${workflowId}/hypotheses`),
      api<{ plan: Plan }>(`/api/v1/workflows/${workflowId}/plan`),
      api<AgentBody>(`/api/v1/workflows/${workflowId}/agents`),
      api<{ items: Execution[] }>(`/api/v1/workflows/${workflowId}/executions`),
      api<{ items: Approval[] }>("/api/v1/approvals"),
    ]);
    setWorkflow(item);
    setHypotheses(hypothesisBody.items);
    setPlan(planBody.plan);
    setAgents(agentBody.items);
    setTools(agentBody.tools);
    setExecutions(executionBody.items);
    setValidation(agentBody.validation || null);
    setNotices(agentBody.notifications || []);
    setChange(agentBody.change || null);
    setApproval(approvals.items.find((row) => row.workflow_id === workflowId && row.status === "pending") || null);
  }

  useEffect(() => {
    load().catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, [workflowId]);

  async function decide(decision: "approve" | "reject") {
    if (!approval) return;
    setError("");
    try {
      await api(`/api/v1/approvals/${approval.id}/${decision}`, { method: "POST", body: JSON.stringify({ reason }) });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Decision failed");
    }
  }

  if (!workflow) return error ? <ErrorNote message={error} /> : <p className="text-sm text-[var(--ink-muted)]">Loading workflow…</p>;

  const triage = agents.find((item) => item.agent_name === "triage");
  const rca = agents.find((item) => item.agent_name === "rca");
  const triageOut = (triage?.output || {}) as {
    impacted_ci?: { name?: string; class?: string; environment?: string; criticality?: string };
    business_service?: { name?: string; criticality?: string };
    priority?: string;
    related_changes?: { number?: string; summary?: string; opened_at?: string }[];
    similar?: { number?: string; title?: string; resolution_summary?: string }[];
    untrusted_notes?: string[];
  };
  const rcaOut = (rca?.output || {}) as {
    logs?: { timestamp?: string; message?: string }[];
    traces?: { trace_id?: string; service?: string; span?: string; duration_ms?: number; message?: string }[];
    traces_error?: string;
    series?: { cpu?: { points?: { value: number }[] }; memory?: { points?: { value: number }[] } };
    confidence_note?: string;
    narrative?: string;
    llm_error?: string;
    model?: string;
  };
  const duration = elapsed(workflow.started_at, workflow.finished_at);
  const cpu = rcaOut.series?.cpu?.points || [];
  const memory = rcaOut.series?.memory?.points || [];
  const correlation = agents.find((item) => item.agent_name === "event_correlation");
  const capacity = agents.find((item) => item.agent_name === "capacity_risk");
  const prevented = agents.find((item) => item.agent_name === "validation");
  const correlationOut = (correlation?.output || {}) as {
    forecast_count?: number;
    alert_count?: number;
    groups?: { summary?: string; alert_count?: number }[];
  };
  const capacityOut = (capacity?.output || {}) as {
    current_utilization?: number;
    growth_per_hour?: number;
    hours_to_exhaustion?: number;
    configuration_item?: { name?: string; class?: string; environment?: string };
    business_service?: { name?: string; criticality?: string };
    related_changes?: { number?: string; summary?: string }[];
    similar_fixes?: { number?: string; summary?: string }[];
    recommended_actions?: string[];
  };
  const preventedOut = (prevented?.output || {}) as {
    before_utilization?: number;
    utilization?: number;
    hours_to_exhaustion?: number;
    incident_avoided?: boolean;
  };

  return (
    <div className="max-w-3xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mono text-[11px] text-[var(--ink-muted)]">{workflow.id}</div>
          <h1 className="mt-1 text-2xl">{workflow.kind === "incident" ? "Claims incident" : workflow.kind === "capacity" ? "Disk capacity" : `${workflow.kind} workflow`}</h1>
        </div>
        <Badge value={workflow.state} />
      </div>
      <p className="mt-2 text-sm text-[var(--ink-muted)]">
        Autonomy {workflow.autonomy_level}
        {workflow.incident_id ? <> · <Link to={`/incidents/${workflow.incident_id}`}>ServiceNow record</Link></> : null}
      </p>
      {workflow.kind === "capacity" ? <p className="mt-2 text-sm text-[var(--ink-muted)]">
        {duration ? `Prediction to remediation took ${duration}.` : "Remediation time is recorded when the DBA approves and the workflow finishes."} L3 holds the certified runbook for the DBA. L4 runs the same runbook when the process flag is on.
      </p> : null}
      {workflow.kind === "incident" ? <p className="mt-2 text-sm text-[var(--ink-muted)]">
        Triage agent {triage?.latency_ms ?? "—"} ms. Target is under 5 minutes.
        {duration ? ` Resolution took ${duration}.` : " Resolution time is recorded when the workflow finishes."} Target at L3 is under 20 minutes. L4 uses this same certified runbook and skips the approval card when the process allows it.
      </p> : null}
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}

      {workflow.kind === "incident" ? <>
      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Triage</h2>
        <div className="card mt-3 space-y-3 px-4 py-3 text-sm">
          <div>CI {triageOut.impacted_ci?.name || "—"} · {triageOut.impacted_ci?.class || "class unknown"} · {triageOut.impacted_ci?.criticality || "criticality unknown"} · {triageOut.impacted_ci?.environment || "environment unknown"}</div>
          <div>Business service {triageOut.business_service?.name || "—"} · priority P{triageOut.priority || "—"}</div>
          <div>Recent changes: {(triageOut.related_changes || []).map((item) => `${item.number} ${item.summary}`).join("; ") || "none returned"}</div>
          <div>Similar incidents: {(triageOut.similar || []).length}</div>
          <ul className="space-y-1 text-[var(--ink-muted)]">
            {(triageOut.similar || []).map((item) => <li key={item.number}>{item.number} · {item.title} · {item.resolution_summary}</li>)}
          </ul>
          <div className="text-[var(--ink-muted)]">Work notes are untrusted and are not used as signals.</div>
          <ul className="space-y-1">{(triageOut.untrusted_notes || []).map((note) => <li key={note}>{note}</li>)}</ul>
        </div>
      </section>

      <section className="mt-8">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm text-[var(--ink-muted)]">RCA evidence</h2>
          <Link to="/rca" className="text-[13px] text-[var(--violet)] hover:underline">Open the RCA page</Link>
        </div>
        <div className="card mt-3 space-y-2 px-4 py-3 text-sm">
          <div>CPU {cpu.map((point) => point.value).join(" → ") || "no samples"}</div>
          <div>Memory {memory.map((point) => point.value).join(" → ") || "no samples"}</div>
          <div>Logs: {(rcaOut.logs || []).map((item) => item.message).join(" ") || "none"}</div>
          <div>Traces: {rcaOut.traces_error || ((rcaOut.traces || []).map((item) => `${item.trace_id} ${item.span} ${item.duration_ms}ms`).join("; ") || "none returned")}</div>
          <div className="text-[var(--ink-muted)]">{rcaOut.confidence_note || "Scores come from measured slopes."}</div>
          {rcaOut.narrative ? <div>Narrative · {rcaOut.model || "model"}: {rcaOut.narrative}</div> : null}
          {rcaOut.llm_error ? <div>Model call failed: {rcaOut.llm_error}</div> : null}
        </div>
        {hypotheses.length === 0 ? <div className="mt-3"><Empty title="No hypotheses" detail="The ranker emits a cause only when a measured signal crosses its threshold." /></div> : (
          <ol className="mt-3 space-y-2">
            {hypotheses.map((item) => (
              <li key={item.rank} className="card px-4 py-3">
                <div className="text-sm">{item.rank}. {item.cause}</div>
                <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]">score {item.confidence} · human review {String(item.requires_human_review)}</div>
                {item.limitations.length ? <div className="mt-1 text-xs text-[var(--ink-muted)]">{item.limitations.join(" · ")}</div> : null}
              </li>
            ))}
          </ol>
        )}
      </section>
      </> : null}

      {workflow.kind === "capacity" ? <>
      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Forecast event</h2>
        <div className="card mt-3 space-y-2 px-4 py-3 text-sm">
          <div>{correlation?.summary || "Dynatrace forecast is grouped with the related disk alerts."}</div>
          <div className="text-[var(--ink-muted)]">{correlationOut.groups?.[0]?.summary || "One actionable event."}</div>
          <div>{capacityOut.current_utilization ?? "—"}% now · {capacityOut.growth_per_hour ?? "—"} points/hour · {capacityOut.hours_to_exhaustion ?? "—"} h to exhaustion</div>
        </div>
      </section>
      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Capacity and risk</h2>
        <div className="card mt-3 space-y-2 px-4 py-3 text-sm">
          <div>CI {capacityOut.configuration_item?.name || "—"} · {capacityOut.configuration_item?.class || "class unknown"} · {capacityOut.configuration_item?.environment || "environment unknown"}</div>
          <div>Business service {capacityOut.business_service?.name || "—"} · {capacityOut.business_service?.criticality || "criticality unknown"}</div>
          <div>Recent changes: {(capacityOut.related_changes || []).map((item) => `${item.number} ${item.summary}`).join("; ") || "none returned"}</div>
          <div>Similar fixes: {(capacityOut.similar_fixes || []).length}</div>
          <ul className="space-y-1 text-[var(--ink-muted)]">
            {(capacityOut.similar_fixes || []).map((item) => <li key={item.number}>{item.number} · {item.summary}</li>)}
          </ul>
          <div>Recommended: {(capacityOut.recommended_actions || []).join("; ") || "no certified action yet"}</div>
        </div>
      </section>
      {preventedOut.utilization != null ? (
        <section className="mt-8">
          <h2 className="text-sm text-[var(--ink-muted)]">Before and after</h2>
          <div className="card mt-3 px-4 py-3 text-sm">
            <div>{preventedOut.before_utilization ?? "—"}% → {preventedOut.utilization}% · {preventedOut.hours_to_exhaustion ?? "—"} h remaining</div>
            <div className="mt-1 text-[var(--ink-muted)]">{preventedOut.incident_avoided ? "No incident raised. Service impact avoided." : "An incident or service impact is still recorded."}</div>
            {change ? <div className="mt-2">Standard change {change.number} · {change.state}</div> : null}
          </div>
        </section>
      ) : null}
      </> : null}

      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Certified runbook</h2>
        {plan ? (
          <div className="card mt-3 px-4 py-3 text-sm">
            <div>{plan.summary}</div>
            <div className="mono mt-2 text-[11px] text-[var(--ink-muted)]">risk {plan.risk_level} · rollback {String(plan.rollback_available)}{plan.parameters.min_age_days ? ` · logs older than ${plan.parameters.min_age_days} days` : ""}{plan.parameters.service_name ? ` · service ${plan.parameters.service_name}` : ""}{plan.parameters.node_count ? ` · nodes ${plan.parameters.node_count}` : ""}</div>
          </div>
        ) : <div className="mt-3"><Empty title="No plan" detail="A plan appears after a certified runbook matches the evidence." /></div>}
      </section>

      {approval ? (
        <section className="card mt-8 p-4">
          <h2 className="text-sm">{approval.required_role === "sre" ? "On-call SRE approval" : approval.required_role === "dba" ? "DBA approval" : `${approval.required_role} approval`}</h2>
          {workflow.kind === "incident" ? <p className="mt-2 text-sm text-[var(--ink-muted)]">L3 holds the certified runbook here. Approving lets the restricted runner perform the sandbox precheck, restart, and one-node record. L4 skips this card for the same runbook when the process flag is on.</p> : null}
          {workflow.kind === "capacity" ? <p className="mt-2 text-sm text-[var(--ink-muted)]">L3 holds the log purge and volume extension for the DBA. Approving runs the sandbox pre-check, cleanup, extension, and post-check. L4 runs this certified runbook without the card when the process flag is on.</p> : null}
          <input className="mt-3 w-full rounded-xl bg-[var(--bg-muted)] px-3 py-2 text-sm outline-none" placeholder="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          <div className="mt-3 flex gap-2">
            <Button onClick={() => decide("approve")}>Approve</Button>
            <Button tone="quiet" onClick={() => decide("reject")}>Reject</Button>
          </div>
        </section>
      ) : null}

      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Execution</h2>
        {executions.length === 0 ? <div className="mt-3"><Empty title="No execution" detail="Execution starts after approval, or automatically when every L4 condition passes." /></div> : executions.map((item) => (
          <div key={item.external_execution_id} className="card mt-3 px-4 py-3 text-sm">
            <div className="flex justify-between"><span>{item.phase}</span><Badge value={item.status} /></div>
            <div className="mono mt-2 text-[11px] text-[var(--ink-muted)]">{item.result.executor || "no executor recorded"}</div>
            <div className="mt-2 text-[var(--ink-muted)]">{(item.result.log || []).join(" · ") || "No task log recorded."}</div>
          </div>
        ))}
      </section>

      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Validation and notification</h2>
        {validation ? (
          <div className="card mt-3 px-4 py-3 text-sm">
            <div className="flex justify-between"><span>{validation.summary}</span><Badge value={validation.status} /></div>
            <ul className="mt-2 space-y-1 text-[var(--ink-muted)]">
              {(validation.checks || []).map((check) => <li key={check.name}>{check.name} · {check.passed ? "passed" : "failed"}</li>)}
            </ul>
          </div>
        ) : <p className="mt-3 text-sm text-[var(--ink-muted)]">Validation runs after the sandbox action.</p>}
        {notices.map((item) => (
          <div key={item.subject + item.body} className="card mt-3 px-4 py-3 text-sm">
            <div>{item.recipient || "operator"} · {item.channel} · {item.status}</div>
            <div className="mt-1 text-[var(--ink-muted)]">{item.body}</div>
          </div>
        ))}
      </section>

      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Agents</h2>
        <ul className="mt-3 space-y-2">
          {agents.map((item) => (
            <li key={item.agent_name + item.summary} className="card px-4 py-3 text-sm">
              <div className="flex justify-between gap-3"><span>{item.agent_name}</span><Badge value={item.status} /></div>
              <div className="mt-1 text-[var(--ink-muted)]">{item.summary}</div>
              <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]">{item.model || "no model call"} · {item.latency_ms ?? "—"} ms</div>
            </li>
          ))}
        </ul>
        <div className="mono mt-3 text-[11px] text-[var(--ink-muted)]">{tools.map((tool) => tool.tool_name).join(" · ") || "No tool calls recorded."}</div>
      </section>
    </div>
  );
}
