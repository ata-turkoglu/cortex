import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export type AFlowNode = Node;
export type AFlowEdge = Edge;
export function AFlowCanvas({
  nodes,
  edges,
  onNodeClick,
  height = 460,
  showMiniMap = false,
  nodeTypes,
}: {
  nodes: AFlowNode[];
  edges: AFlowEdge[];
  onNodeClick?: (id: string) => void;
  height?: number;
  showMiniMap?: boolean;
  nodeTypes?: NodeTypes;
}) {
  return (
    <div style={{ height }}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView onNodeClick={(_, node) => onNodeClick?.(node.id)}>
        <Background />
        {showMiniMap && <MiniMap />}
        <Controls />
      </ReactFlow>
    </div>
  );
}
