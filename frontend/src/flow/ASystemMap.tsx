import type { Edge, Node } from "@xyflow/react";
import { AFlowCanvas } from "./AFlowCanvas";

const nodes: Node[] = [
  { id: "ui", position: { x: 0, y: 80 }, data: { label: "Frontend" } },
  { id: "api", position: { x: 220, y: 80 }, data: { label: "Backend API" } },
  { id: "worker", position: { x: 440, y: 0 }, data: { label: "Worker" } },
  {
    id: "stores",
    position: { x: 440, y: 160 },
    data: { label: "SQLite · Redis · Qdrant" },
  },
];
const edges: Edge[] = [
  { id: "ui-api", source: "ui", target: "api" },
  { id: "api-worker", source: "api", target: "worker" },
  { id: "api-stores", source: "api", target: "stores" },
  { id: "worker-stores", source: "worker", target: "stores" },
];
export function ASystemMap() {
  return <AFlowCanvas nodes={nodes} edges={edges} />;
}
