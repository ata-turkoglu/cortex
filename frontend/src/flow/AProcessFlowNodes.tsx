import { Handle, Position, type Node, type NodeProps, type NodeTypes } from "@xyflow/react";

export type ProcessNodeKind = "prepare" | "processor" | "embedding" | "api" | "storage" | "maintenance";
export type ProcessNodeData = { title: string; description: string; technology: string; status: string; kind: ProcessNodeKind };
export type ProcessNode = Node<ProcessNodeData, "process">;
export type ProcessGroupNode = Node<{ title: string; status: string }, "process-group">;

const kindPresentation: Record<ProcessNodeKind, { label: string; color: string; soft: string }> = {
  prepare: { label: "Hazırlık", color: "#5e81ac", soft: "#edf3f9" }, processor: { label: "İşleme", color: "#3b8ea5", soft: "#e8f5f7" }, embedding: { label: "Embedding · Local", color: "#8f6fae", soft: "#f4eef8" }, api: { label: "LLM · API", color: "#c07a3e", soft: "#fbf1e7" }, storage: { label: "Kalıcı kayıt", color: "#4c566a", soft: "#edf0f4" }, maintenance: { label: "Bakım", color: "#718096", soft: "#f1f5f9" },
};
const statusPresentation: Record<string, { label: string; color: string; soft: string }> = {
  unknown: { label: "Doğrulanamadı", color: "#64748b", soft: "#f1f5f9" },
  pending: { label: "Bekliyor", color: "#64748b", soft: "#f1f5f9" }, queued: { label: "Kuyrukta", color: "#64748b", soft: "#f1f5f9" }, running: { label: "Çalışıyor", color: "#2563eb", soft: "#eff6ff" }, completed: { label: "Tamamlandı", color: "#15803d", soft: "#ecfdf3" }, failed: { label: "Başarısız", color: "#dc2626", soft: "#fef2f2" }, cancelling: { label: "İptal ediliyor", color: "#b45309", soft: "#fffbeb" }, cancelled: { label: "İptal edildi", color: "#b45309", soft: "#fffbeb" }, interrupted: { label: "Kesildi", color: "#b45309", soft: "#fffbeb" },
};

function ProcessNodeCard({ data, selected }: NodeProps<ProcessNode>) {
  const kind = kindPresentation[data.kind];
  const status = statusPresentation[data.status] ?? statusPresentation.pending;
  return <article style={{ background: "var(--cortex-panel)", border: `1px solid ${selected ? kind.color : "var(--cortex-line)"}`, borderLeft: `5px solid ${kind.color}`, borderRadius: "var(--cortex-radius)", boxShadow: selected ? `0 0 0 2px ${kind.soft}` : "0 2px 7px rgb(15 23 42 / 8%)", display: "grid", gap: 8, minHeight: 152, padding: "12px 13px" }}>
    <Handle id="target-left" type="target" position={Position.Left} style={{ background: kind.color, border: 0 }} />
    <Handle id="target-right" type="target" position={Position.Right} style={{ background: kind.color, border: 0 }} />
    <Handle id="target-top" type="target" position={Position.Top} style={{ background: kind.color, border: 0 }} />
    <div style={{ alignItems: "center", display: "flex", gap: 8, justifyContent: "space-between" }}><span style={{ color: kind.color, fontSize: 10, fontWeight: 800, letterSpacing: ".04em", textTransform: "uppercase" }}>{kind.label}</span><span style={{ background: status.soft, border: `1px solid ${status.color}`, borderRadius: 999, color: status.color, fontSize: 10, fontWeight: 800, padding: "2px 7px", whiteSpace: "nowrap" }}>{status.label}</span></div>
    <strong style={{ color: "var(--cortex-text)", fontSize: 14, lineHeight: 1.25 }}>{data.title}</strong>
    <p style={{ color: "var(--cortex-muted)", display: "-webkit-box", fontSize: 11, lineHeight: 1.4, margin: 0, overflow: "hidden", WebkitBoxOrient: "vertical", WebkitLineClamp: 3 }}>{data.description}</p>
    <span style={{ color: kind.color, fontSize: 10, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{data.technology}</span>
    <Handle id="source-right" type="source" position={Position.Right} style={{ background: kind.color, border: 0 }} />
    <Handle id="source-left" type="source" position={Position.Left} style={{ background: kind.color, border: 0 }} />
    <Handle id="source-bottom" type="source" position={Position.Bottom} style={{ background: kind.color, border: 0 }} />
  </article>;
}

function ProcessGroup({ data }: NodeProps<ProcessGroupNode>) {
  const status = statusPresentation[data.status] ?? statusPresentation.pending;
  return <section style={{ background: "color-mix(in srgb, var(--cortex-primary-soft) 48%, transparent)", border: "1px solid var(--cortex-line)", borderRadius: "calc(var(--cortex-radius) + 4px)", boxSizing: "border-box", height: "100%", padding: "18px 20px", pointerEvents: "none", width: "100%" }}><div style={{ alignItems: "center", display: "flex", gap: 8 }}><strong style={{ color: "var(--cortex-text)", fontSize: 13 }}>{data.title}</strong><span style={{ color: status.color, fontSize: 11, fontWeight: 750 }}>{status.label}</span></div><span style={{ color: "var(--cortex-muted)", fontSize: 11 }}>Dayanıklı workflow aşamaları</span></section>;
}

export const processNodeTypes: NodeTypes = { process: ProcessNodeCard, "process-group": ProcessGroup };
