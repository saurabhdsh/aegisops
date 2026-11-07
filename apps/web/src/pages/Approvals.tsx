import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Badge, Button, Empty, ErrorNote } from "../components/ui";

type Approval = { id: string; workflow_id: string; required_role: string; status: string; runbook_version: string; plan_hash: string };

export function Approvals() {
  const [items, setItems] = useState<Approval[]>([]);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("checked");

  async function load() {
    const page = await api<{ items: Approval[] }>("/api/v1/approvals");
    setItems(page.items);
  }

  useEffect(() => {
    load().catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, []);

  async function decide(id: string, decision: "approve" | "reject") {
    setError("");
    try {
      await api(`/api/v1/approvals/${id}/${decision}`, { method: "POST", body: JSON.stringify({ reason }) });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Decision failed");
    }
  }

  return (
    <div>
      <h1 className="text-2xl">Approvals</h1>
      <p className="mt-1 text-sm text-[var(--ink-muted)]">The policy engine decides whether a human is required. This screen records that decision.</p>
      <input className="mt-4 w-full max-w-md rounded-xl bg-[var(--bg-muted)] px-3 py-2 text-sm outline-none" value={reason} onChange={(event) => setReason(event.target.value)} />
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}
      {items.length === 0 ? <div className="mt-6"><Empty title="No approval requests" detail="A workflow creates one when automatic execution is not allowed." /></div> : (
        <ul className="mt-6 space-y-2">
          {items.map((item) => (
            <li key={item.id} className="card px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <Link to={`/workflows/${item.workflow_id}`} className="text-sm">{item.required_role === "sre" ? "On-call SRE" : item.required_role === "dba" ? "DBA" : item.required_role} · {item.runbook_version}</Link>
                <Badge value={item.status} />
              </div>
              <div className="mono mt-2 truncate text-[11px] text-[var(--ink-muted)]">{item.plan_hash}</div>
              {item.status === "pending" ? (
                <div className="mt-3 flex gap-2">
                  <Button onClick={() => decide(item.id, "approve")}>Approve</Button>
                  <Button tone="quiet" onClick={() => decide(item.id, "reject")}>Reject</Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
