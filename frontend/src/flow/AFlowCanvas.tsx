import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export type AFlowNode = Node;
export type AFlowEdge = Edge;
export function AFlowCanvas({
  nodes,
  edges,
  onNodeClick,
}: {
  nodes: AFlowNode[];
  edges: AFlowEdge[];
  onNodeClick?: (id: string) => void;
}) {
  return (
    <div style={{ height: 360 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView onNodeClick={(_, node) => onNodeClick?.(node.id)}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
