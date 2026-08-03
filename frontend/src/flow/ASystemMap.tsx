import type { Edge, Node } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../api/client";
import { AInfo } from "../ui/primitives";
import { AFlowCanvas } from "./AFlowCanvas";

const edges: Edge[] = [
  { id: "api-worker", source: "backend", target: "worker" },
  { id: "api-sqlite", source: "backend", target: "sqlite" },
  { id: "worker-redis", source: "worker", target: "redis" },
  { id: "worker-qdrant", source: "worker", target: "qdrant" },
];
export function ASystemMap() {
  const [services, setServices] = useState<Record<string, string>>({ backend: "unknown" });
  const [selected, setSelected] = useState("backend");
  useEffect(() => {
    const refresh = () => Promise.all([apiClient.getHealth(), apiClient.diagnostics()]).then(([health, diagnostics]) => setServices({ ...health.services, recovery: diagnostics.workflows.interrupted ? "attention" : "healthy", reconciliation: diagnostics.reconciliation.state })).catch(() => setServices({ backend: "unavailable" }));
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(timer);
  }, []);
  const nodes = useMemo<Node[]>(() => Object.entries(services).map(([id, status], index) => ({
    id, position: { x: (index % 3) * 220, y: Math.floor(index / 3) * 110 },
    data: { label: `${id.replace("_", " ")} · ${status}` },
    style: { borderColor: status === "healthy" || status === "configured" ? "#16a34a" : status === "unavailable" ? "#dc2626" : "#ca8a04", borderWidth: 2 },
  })), [services]);
  const visibleEdges = edges.filter((edge) => nodes.some((node) => node.id === edge.source) && nodes.some((node) => node.id === edge.target));
  return <><AInfo title="System component">{selected.replace("_", " ")}: {services[selected] ?? "unknown"}. Status is refreshed from backend health checks.</AInfo><div className="mt-3"><AFlowCanvas nodes={nodes} edges={visibleEdges} onNodeClick={setSelected} /></div></>;
}
