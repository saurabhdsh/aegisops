import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button, Empty, ErrorNote } from "../components/ui";

type AuditRow = { id: string; action: string; resource_type: string; resource_id: string; created_at: string };
type Controls = { emergency_stop: boolean; autonomy_level: string; freeze_reason: string };

export function Audit() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [controls, setControls] = useState<Controls | null>(null);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");

  async function load() {
    const [audit, control] = await Promise.all([
      api<{ items: AuditRow[] }>("/api/v1/audit"),
      api<Controls>("/api/v1/operations/controls"),
    ]);
    setRows(audit.items);
    setControls(control);
  }

  useEffect(() => {
    load().catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, []);

  async function stop() {
    setError("");
    try {
      await api("/api/v1/operations/emergency-stop", { method: "POST", body: JSON.stringify({ reason }) });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Emergency stop failed");
    }
  }

  async function clearStop() {
    setError("");
    try {
      await api("/api/v1/operations/emergency-stop/clear", { method: "POST", body: JSON.stringify({ reason }) });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Clear failed");
    }
  }

  return (
    <div>
      <h1 className="text-2xl">Audit and controls</h1>
      <p className="mt-1 text-sm text-[var(--ink-muted)]">Emergency stop blocks new approvals and executions. It does not claim an action already sent to an external system has stopped.</p>
      {controls ? (
        <div className="card mt-6 px-4 py-3 text-sm">
          <div>Autonomy {controls.autonomy_level}</div>
          <div className="mt-1">Emergency stop {controls.emergency_stop ? "active" : "off"}{controls.freeze_reason ? ` · ${controls.freeze_reason}` : ""}</div>
          <input className="mt-3 w-full rounded-xl bg-[var(--bg-muted)] px-3 py-2 outline-none" placeholder="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          <div className="mt-3 flex gap-2">
            <Button onClick={stop}>Engage emergency stop</Button>
            <Button tone="quiet" onClick={clearStop}>Clear emergency stop</Button>
          </div>
        </div>
      ) : null}
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}
      <section className="mt-8">
        <h2 className="text-sm text-[var(--ink-muted)]">Audit events</h2>
        {rows.length === 0 ? <div className="mt-3"><Empty title="No audit events" detail="Sign-in, approvals, and control changes append events. Existing rows cannot be edited." /></div> : (
          <ul className="mt-3 space-y-2">
            {rows.map((row) => (
              <li key={row.id} className="card px-4 py-3 text-sm">
                <div>{row.action}</div>
                <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]">{row.resource_type} {row.resource_id}</div>
                <div className="mono mt-1 text-[11px] text-[var(--titanium)]">{row.created_at}</div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
