import { useEffect, useState } from "react";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../lib/api";
import { Empty, ErrorNote } from "../components/ui";

type Service = { id: string; name: string; criticality: string };
type Item = { id: string; name: string; business_service_id: string | null; environment: string };

export function Topology() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [error, setError] = useState("");
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    Promise.all([
      api<{ items: Service[] }>("/api/v1/topology/services"),
      api<{ items: Item[] }>("/api/v1/topology/configuration-items"),
    ])
      .then(([services, items]) => {
        if (services.items.length === 0 && items.items.length === 0) {
          setEmpty(true);
          return;
        }
        const nextNodes: Node[] = [
          ...services.items.map((service, index) => ({
            id: service.id,
            position: { x: 40, y: index * 110 },
            data: { label: `${service.name} · ${service.criticality}` },
            style: { background: "#14161b", color: "#e7e8ea", border: "1px solid rgba(232,234,237,0.1)", width: 220 },
          })),
          ...items.items.map((item, index) => ({
            id: item.id,
            position: { x: 360, y: index * 110 },
            data: { label: `${item.name} · ${item.environment}` },
            style: { background: "#1b1e25", color: "#e7e8ea", border: "1px solid rgba(232,234,237,0.1)", width: 220 },
          })),
        ];
        const nextEdges: Edge[] = items.items
          .filter((item) => item.business_service_id)
          .map((item) => ({ id: `${item.business_service_id}-${item.id}`, source: item.business_service_id as string, target: item.id }));
        setNodes(nextNodes);
        setEdges(nextEdges);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Load failed"));
  }, []);

  return (
    <div>
      <h1 className="text-2xl">Topology</h1>
      <p className="mt-1 text-sm text-[var(--ink-muted)]">Services and configuration items stored for this tenant.</p>
      {error ? <div className="mt-4"><ErrorNote message={error} /></div> : null}
      {empty ? <div className="mt-6"><Empty title="No topology" detail="Services and hosts appear when CMDB records are available." /></div> : (
        <div className="card mt-6 h-[560px] overflow-hidden">
          <ReactFlow nodes={nodes} edges={edges} fitView colorMode="dark">
            <Background />
            <Controls />
          </ReactFlow>
        </div>
      )}
    </div>
  );
}
