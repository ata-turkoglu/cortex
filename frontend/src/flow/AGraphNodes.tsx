import { Handle, Position, type Node, type NodeProps, type NodeTypes } from "@xyflow/react";
import { useId } from "react";

export type GraphNodeKind =
  | "input"
  | "service"
  | "processor"
  | "decision"
  | "storage"
  | "retrieval"
  | "llm-local";

export type GraphNodeData = {
  label: string;
  description: string;
  entityType: string;
  kind: GraphNodeKind;
  descriptionOpen?: boolean;
  onDescriptionToggle?: (id: string) => void;
};

export type GraphNode = Node<GraphNodeData, "graph-entity">;

const typePresentation: Array<[RegExp, GraphNodeKind, string]> = [
  [/person|people|human|user|contact/i, "input", "Kişi"],
  [/organization|organisation|company|team|group/i, "service", "Organizasyon"],
  [/location|place|address|city|country/i, "retrieval", "Konum"],
  [/event|date|incident/i, "processor", "Olay"],
  [/product|technology|software|tool/i, "llm-local", "Ürün / teknoloji"],
  [/concept|topic|idea|theory/i, "decision", "Kavram"],
];

export function graphNodePresentation(attributes: Record<string, string>) {
  const rawType = attributes.type ?? attributes.entity_type ?? attributes.category ?? "entity";
  const match = typePresentation.find(([pattern]) => pattern.test(rawType));
  return {
    kind: match?.[1] ?? "storage",
    entityType: match?.[2] ?? "Diğer varlık",
  } satisfies Pick<GraphNodeData, "kind" | "entityType">;
}

function GraphEntityNode({ data, id, selected }: NodeProps<GraphNode>) {
  const descriptionId = useId();
  const description = data.description || "Açıklama bulunmuyor.";

  return (
    <article className={`architecture-node graph-entity-node is-${data.kind}${selected ? " is-selected" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <button
        type="button"
        className="graph-entity-node__trigger nodrag"
        aria-expanded={data.descriptionOpen}
        aria-describedby={data.descriptionOpen ? descriptionId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          data.onDescriptionToggle?.(id);
        }}
      >
        <strong>{data.label}</strong>
      </button>
      {data.descriptionOpen && <span id={descriptionId} role="tooltip" className="graph-entity-node__tooltip">{description}</span>}
      <Handle type="source" position={Position.Right} />
    </article>
  );
}

export const graphNodeTypes: NodeTypes = { "graph-entity": GraphEntityNode };
