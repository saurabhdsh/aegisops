import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button, Empty, ErrorNote } from "../components/ui";

type Runbook = { id: string; slug: string; version: string; name: string; checksum: string; rollback_defined: boolean };
type Certification = { status: string; certified_by: string; expires_at: string | null; scope: { external_ids?: string[] } | null };

export function Runbooks() {
  const [items, setItems] = useState<Array<Runbook & { certification: Certification[] }>>([]);
  const [probes, setProbes] = useState<string>("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Runbook[]>("/api/v1/runbooks")
      .then(async (rows) => {
        const detailed = await Promise.all(
          rows.map(async (row) => ({
            ...row,
            certification: await api<Certification[]>(`/api/v1/runbooks/${row.id}/certification`),
          })),
        );
        setItems(detailed);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, []);

  async function probe() {
    setError("");
    try {
      const snow = await api<{ mode?: string; status: string }>("/api/v1/integrations/servicenow/test", { method: "POST" });
      const dyna = await api<{ capabilities?: Record<string, string>; status: string }>("/api/v1/integrations/dynatrace/test", { method: "POST" });
      setProbes(`ServiceNow ${snow.status} ${snow.mode || ""}. Dynatrace ${dyna.status}. Traces ${dyna.capabilities?.traces || "unknown"}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Probe failed");
    }
  }

  return (
    <div>
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl">Runbooks</h1>
          <p className="mt-1 text-sm text-[var(--ink-muted)]">Certified runbooks the remediation agent is allowed to select.</p>
        </div>
        <Button className="shrink-0" onClick={probe}>Probe connectors</Button>
      </div>
      {probes ? <p className="mt-4 text-sm text-[var(--cyan)]">{probes}</p> : null}
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}
      {items.length === 0 ? <div className="mt-6"><Empty title="No runbooks" detail="Certified runbooks appear here once they are registered for a target." /></div> : (
        <ul className="mt-6 space-y-2">
          {items.map((item) => (
            <li key={item.id} className="card px-4 py-3 text-sm">
              <div>{item.name}</div>
              <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]">{item.slug}@{item.version} · rollback {String(item.rollback_defined)}</div>
              <div className="mono mt-1 break-all text-[11px] text-[var(--titanium)]">{item.checksum}</div>
              <div className="mt-2 text-xs text-[var(--ink-muted)]">
                {(item.certification[0]?.status || "uncertified")} · {item.certification[0]?.certified_by || "nobody"} · scope {(item.certification[0]?.scope?.external_ids || []).join(", ") || "none"}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
