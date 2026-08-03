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
}: {
  nodes: AFlowNode[];
  edges: AFlowEdge[];
}) {
  return (
    <div style={{ height: 360 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
