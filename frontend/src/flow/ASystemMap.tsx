import {
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../api/client";
import { ACard, AInfoPanel, ATabs } from "../components/ui";
import { AFlowCanvas } from "./AFlowCanvas";

type MapTab = "system" | "ingestion" | "query" | "workflows";
type DetailTab =
  | "description"
  | "interfaces"
  | "guarantee"
  | "documentation"
  | "context";
type NodeKind =
  | "input"
  | "service"
  | "processor"
  | "decision"
  | "storage"
  | "retrieval"
  | "llm-local"
  | "llm-api"
  | "safety"
  | "worker"
  | "delivery";
const nodeCategoryLabels: Record<NodeKind, string> = {
  input: "Veri girişi",
  processor: "Veri işleme",
  decision: "Yönlendirme",
  safety: "Güvenlik",
  storage: "Kalıcı veri",
  retrieval: "Retrieval",
  worker: "Arka plan",
  delivery: "Teslim",
  service: "Servis",
  "llm-local": "LLM",
  "llm-api": "LLM",
};
const MAP_NODE_WIDTH = 205;
const MAP_NODE_MIN_HEIGHT = 160;
const MAP_NODE_HORIZONTAL_GAP = 100;
const MAP_NODE_VERTICAL_GAP = 80;
const MAP_GROUP_HORIZONTAL_PADDING = 100;
const MAP_GROUP_VERTICAL_PADDING = 80;
type RecordKind = "database" | "file" | "vector" | "cache";
type MapNodeData = {
  label: string;
  description: string;
  interfaces: string;
  guarantee: string;
  kind: NodeKind;
  layer: string;
  model?: string;
  recordKind?: RecordKind;
  documentation?: string;
  context?: string;
};
type MapNode = Node<MapNodeData, "architecture">;
type FlowGroupVariant =
  | "platform"
  | "input"
  | "processing"
  | "durable"
  | "dense"
  | "graphrag"
  | "query"
  | "delivery";
type FlowGroupNode = Node<
  {
    label: string;
    variant: FlowGroupVariant;
    boundary?: string;
    documentation?: string;
    context?: string;
  },
  "flow-group"
>;

export type SystemMapSubsystem = {
  id: string;
  label: string;
  boundary: string;
  documentation: string;
  context: string;
  description: string;
  guarantee: string;
  kind: NodeKind;
  variant: FlowGroupVariant;
};

const legendGroups: Array<{
  label: string;
  items: Array<{ kind: NodeKind; label: string }>;
}> = [
  {
    label: "Akış",
    items: [
      { kind: "input", label: "Veri girişi" },
      { kind: "processor", label: "Veri işleme" },
      { kind: "decision", label: "Yönlendirme" },
      { kind: "worker", label: "Arka plan" },
      { kind: "delivery", label: "Teslim" },
    ],
  },
  {
    label: "Veri",
    items: [
      { kind: "storage", label: "Kalıcı veri" },
      { kind: "retrieval", label: "Retrieval" },
    ],
  },
  { label: "Koruma", items: [{ kind: "safety", label: "Güvenlik" }] },
  {
    label: "LLM",
    items: [
      { kind: "llm-local", label: "Local" },
      { kind: "llm-api", label: "API" },
    ],
  },
  { label: "Platform", items: [{ kind: "service", label: "Servis" }] },
];

const tabLabels: Record<MapTab, string> = {
  system: "Canlı sistem",
  ingestion: "Indexing V2",
  query: "Query V2",
  workflows: "Arka plan işlemleri",
};

const staticMaps: Record<
  Exclude<MapTab, "system">,
  { nodes: MapNode[]; edges: Edge[] }
> = {
  ingestion: { nodes: [], edges: [] },
  query: { nodes: [], edges: [] },
  workflows: {
    nodes: [
      node(
        "ui",
        0,
        360,
        "Cortex arayüzü",
        "Yükleme, silme, reindex ve kurtarma komutları.",
        "REST commands",
        "İşler gezinmeden sonra da sürer.",
      ),
      node(
        "api",
        320,
        360,
        "FastAPI komutu",
        "Komutu doğrular, kalıcı run ve step kayıtlarını oluşturur.",
        "/api/v1/workflows",
        "Hatalar standardize edilmiş envelope döner.",
      ),
      node(
        "definition",
        640,
        360,
        "Sürümlü workflow tanımı",
        "Komutun izinli adımları ve retry sınırları seçilir.",
        "Versioned definitions",
        "Uygulanan adımlar kayıtlı tanımla tutarlıdır.",
      ),
      node(
        "state",
        960,
        160,
        "Kalıcı run kaydı",
        "Run, adım, olay, lock ve recovery state saklanır.",
        "workflow_runs / workflow_step_runs",
        "Safe checkpoint’ten retry yapılır.",
      ),
      node(
        "lock-decision",
        960,
        500,
        "Workspace lock uygun mu?",
        "Tehlikeli eşzamanlı komutlar için workspace kilidi kontrol edilir.",
        "Workspace lock record",
        "Çakışan mutasyonlar aynı anda yürütülmez.",
      ),
      node(
        "workflow-redis",
        1450,
        500,
        "Redis + Dramatiq",
        "İş teslimi ve worker çalıştırma sınırı.",
        "Dramatiq broker",
        "API yeniden başlasa bile run kaydı korunur.",
      ),
      node(
        "workflow-worker",
        1755,
        500,
        "Worker",
        "Ingestion, reindex, GraphRAG ve bakım workflow’larını yürütür.",
        "Versioned definitions",
        "Yan etkili adımlar idempotent tasarlanır.",
      ),
      node(
        "checkpoint",
        1920,
        300,
        "Atomik checkpoint",
        "Başarılı adım sonucu ve sonraki adım atomik kaydedilir.",
        "Step run + checkpoint",
        "Yeniden deneme güvenli noktadan başlar.",
      ),
      node(
        "retry-decision",
        2240,
        160,
        "Retry gerekli mi?",
        "Hata, retry politikası ve iptal sinyali değerlendirilir.",
        "Recovery policy",
        "Terminal hata görünür şekilde kalıcıdır.",
      ),
      node(
        "cancel",
        2240,
        500,
        "İptal / recovery komutu",
        "Kullanıcı iptali veya kesilmiş run kurtarma isteği.",
        "REST recovery command",
        "İptal checkpoint sınırında uygulanır.",
      ),
      node(
        "sse",
        2560,
        300,
        "SSE olay akışı",
        "UI canlı ilerlemeyi izler; bağlantı kesilince geçmişten geri yükler.",
        "GET /workflows/{id}/events",
        "Yalnızca gerçekleşen aşamalar gösterilir.",
      ),
    ],
    edges: links(
      ["ui", "api"],
      ["api", "definition"],
      ["definition", "state"],
      ["definition", "lock-decision"],
      ["lock-decision", "workflow-redis", "kilit alındı"],
      ["lock-decision", "state", "çakışma"],
      ["workflow-redis", "workflow-worker"],
      ["workflow-worker", "checkpoint"],
      ["checkpoint", "retry-decision"],
      ["retry-decision", "workflow-worker", "devam"],
      ["retry-decision", "sse", "tamamlandı"],
      ["retry-decision", "cancel", "iptal / hata"],
      ["cancel", "state"],
      ["checkpoint", "state"],
      ["state", "sse"],
      ["sse", "ui"],
    ),
  },
};

const QUERY_V2_SUBSYSTEMS: SystemMapSubsystem[] = [
  {
    id: "v2-query-conversation-context",
    label: "Conversation Context",
    boundary: "backend/app/query/context/",
    documentation: "docs/architecture/query-v2/query-runtime.md",
    context: "backend/app/query/context/AGENTS.md · CLAUDE.md",
    description:
      "Loads durable conversation-local summaries, entities, temporal anchors, and unresolved references within one workspace.",
    guarantee:
      "Conversation memory never becomes workspace-global canonical knowledge and cannot cross a workspace boundary.",
    kind: "storage",
    variant: "input",
  },
  {
    id: "v2-query-understanding",
    label: "Query Understanding",
    boundary: "backend/app/query/understanding/",
    documentation: "docs/architecture/query-v2/query-runtime.md",
    context: "backend/app/query/understanding/AGENTS.md · CLAUDE.md",
    description:
      "Produces constrained semantic meaning, ambiguity, unresolved references, temporal semantics, and follow-up carry-over without a V2 intent field.",
    guarantee:
      "Invalid or ambiguous model output is repaired within bounds or returned as an explicit unresolved state.",
    kind: "processor",
    variant: "processing",
  },
  {
    id: "v2-query-ir",
    label: "Query IR",
    boundary: "backend/app/query/ir/",
    documentation: "docs/architecture/query-v2/invariants.md",
    context: "backend/app/query/ir/AGENTS.md · CLAUDE.md",
    description:
      "Lowers semantic meaning into the versioned, typed Logical Query IR DAG.",
    guarantee:
      "Schema, operator types, dependencies, workspace scope, and evidence requirements validate before planning.",
    kind: "processor",
    variant: "query",
  },
  {
    id: "v2-query-execution-planning",
    label: "Execution Planning",
    boundary: "backend/app/query/planning/ · backend/app/query/execution.py",
    documentation: "docs/architecture/query-v2/execution-planning.md",
    context: "backend/app/query/planning/AGENTS.md · CLAUDE.md",
    description:
      "Builds the physical DAG; its dormant V2 executor resolves one GenerationScope before dense and sparse generation-bound reads.",
    guarantee:
      "Internal dense reads require workspace + generation + embedding hash; sparse reads use only the matching candidate BM25 artifact; V1 chat remains active.",
    kind: "decision",
    variant: "durable",
  },
  {
    id: "v2-query-structured",
    label: "Structured Query",
    boundary: "backend/app/engines/structured/",
    documentation: "docs/architecture/query-v2/structured-graph-engines.md",
    context: "backend/app/engines/structured/AGENTS.md · CLAUDE.md",
    description:
      "Executes exact list, count, distinct, grouping, projection, ranking, and bounded population operations over canonical records.",
    guarantee:
      "Verified exhaustive results require the planned active generation and report their processed population and completeness.",
    kind: "retrieval",
    variant: "query",
  },
  {
    id: "v2-query-knowledge-graph",
    label: "Knowledge Graph",
    boundary: "backend/app/engines/graph/ · backend/app/knowledge/graph/",
    documentation: "docs/architecture/query-v2/structured-graph-engines.md",
    context:
      "backend/app/engines/graph/AGENTS.md · backend/app/knowledge/graph/AGENTS.md",
    description:
      "Queries workspace- and generation-scoped canonical Neo4j entities, relations, events, temporals, claims, facts, conflicts, and provenance.",
    guarantee:
      "CanonicalKnowledge is distinct from GraphRAG extracted artifacts and preserves evidence and curation precedence.",
    kind: "retrieval",
    variant: "query",
  },
  {
    id: "v2-query-retrieval",
    label: "Retrieval",
    boundary: "backend/app/engines/hybrid/ · backend/app/retrieval/",
    documentation: "docs/architecture/retrieval-boundaries.md",
    context:
      "backend/app/engines/hybrid/AGENTS.md · backend/app/retrieval/AGENTS.md",
    description:
      "Dormant V2 adapters execute planned Qdrant and candidate-owned BM25 reads with one immutable scope; fusion remains pending.",
    guarantee:
      "V2 dense reads require workspace + knowledge generation + embedding hash; sparse reads validate candidate artifact identity and never retry legacy workspace BM25.",
    kind: "retrieval",
    variant: "dense",
  },
  {
    id: "v2-query-graphrag",
    label: "GraphRAG",
    boundary: "backend/app/graphrag/",
    documentation: "docs/architecture/graphrag-boundary.md",
    context: "backend/app/graphrag/AGENTS.md · CLAUDE.md",
    description:
      "Runs Microsoft GraphRAG Local, Global, or DRIFT as planned capabilities over extracted GraphRAG projections.",
    guarantee:
      "GraphRAG output is a typed non-final finding; it is not canonical truth and does not author the final answer.",
    kind: "retrieval",
    variant: "graphrag",
  },
  {
    id: "v2-query-result-evidence",
    label: "Result & Evidence",
    boundary: "backend/app/query/orchestration/",
    documentation: "docs/architecture/query-v2/result-evidence-layer.md",
    context: "backend/app/query/orchestration/AGENTS.md · CLAUDE.md",
    description:
      "Reconciles typed EngineResult values and exact evidence from every planned engine into one ReasoningPackage.",
    guarantee:
      "All engines converge here; disagreement, ambiguity, partial failure, provenance, and completeness remain visible.",
    kind: "safety",
    variant: "delivery",
  },
  {
    id: "v2-query-reasoning",
    label: "Reasoning & Composition",
    boundary: "backend/app/reasoning/",
    documentation: "docs/architecture/query-v2/reasoning-composition.md",
    context:
      "backend/app/reasoning/AGENTS.md · research/AGENTS.md · composition/AGENTS.md",
    description:
      "Supports durable decomposition, cross-source research, resumable grounded drafting, and consistency validation.",
    guarantee:
      "Every factual sentence retains collected evidence lineage and incomplete research cannot become a falsely complete artifact.",
    kind: "processor",
    variant: "durable",
  },
  {
    id: "v2-query-answer",
    label: "Answer",
    boundary: "backend/app/chat/execution.py",
    documentation: "docs/architecture/query-answer-pipeline.md",
    context: "backend/AGENTS.md",
    description:
      "Renders the grounded, partial, or unsupported user-facing answer from the validated evidence or composition artifact.",
    guarantee:
      "V1 chat remains active until Phase 13; the V2 answer path cannot activate before the sharp-cutover gate.",
    kind: "delivery",
    variant: "delivery",
  },
];

const INDEXING_V2_SUBSYSTEMS: SystemMapSubsystem[] = [
  {
    id: "v2-index-source",
    label: "Source Processing",
    boundary: "backend/app/ingestion/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/AGENTS.md",
    description:
      "Validates, fingerprints, parses, and normalizes workspace source versions into an immutable corpus snapshot.",
    guarantee:
      "Source IO and parsing run outside SQLite transactions; snapshot membership is workspace-scoped and reproducible.",
    kind: "input",
    variant: "input",
  },
  {
    id: "v2-index-document-structure",
    label: "Document Structure",
    boundary: "backend/app/ingestion/ · backend/app/knowledge/provenance/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/provenance/AGENTS.md · CLAUDE.md",
    description:
      "Materializes document versions, logical documents, chunks, and exact source-span lineage.",
    guarantee:
      "Every extracted assertion can resolve Workspace → Document → Version → LogicalDocument → Chunk → exact span.",
    kind: "storage",
    variant: "processing",
  },
  {
    id: "v2-index-entity-mention",
    label: "Entity / Mention",
    boundary: "backend/app/knowledge/entities/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/entities/AGENTS.md · CLAUDE.md",
    description:
      "Extracts typed entity proposals and original mentions with strict exact-span evidence.",
    guarantee:
      "Provider output is a proposal; invalid spans and dependent assertions are rejected before promotion.",
    kind: "processor",
    variant: "processing",
  },
  {
    id: "v2-index-identity",
    label: "Identity",
    boundary: "backend/app/knowledge/entities/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/entities/AGENTS.md · CLAUDE.md",
    description:
      "Applies conservative, reversible identity resolution using stable opaque canonical IDs.",
    guarantee:
      "Ambiguous mentions remain unresolved and user-curated decisions outrank validated and extracted proposals.",
    kind: "safety",
    variant: "processing",
  },
  {
    id: "v2-index-relation",
    label: "Relation",
    boundary: "backend/app/knowledge/relations/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/relations/AGENTS.md · CLAUDE.md",
    description:
      "Constructs typed, provenance-bearing relations between resolved canonical subjects and objects.",
    guarantee:
      "Co-occurrence alone is never relation evidence and cross-workspace references are rejected.",
    kind: "processor",
    variant: "processing",
  },
  {
    id: "v2-index-event",
    label: "Event",
    boundary: "backend/app/knowledge/events/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/events/AGENTS.md · CLAUDE.md",
    description:
      "Builds typed events and evidence-linked participant roles from validated extraction proposals.",
    guarantee:
      "Event participants and source assertions resolve within the same workspace and generation.",
    kind: "processor",
    variant: "processing",
  },
  {
    id: "v2-index-temporal",
    label: "Temporal",
    boundary: "backend/app/knowledge/temporal/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/temporal/AGENTS.md · CLAUDE.md",
    description:
      "Preserves original temporal text while recording normalized values, ranges, roles, precision, and uncertainty.",
    guarantee:
      "Approximate or unknown dates remain uncertain; normalized values never erase the original source expression.",
    kind: "processor",
    variant: "processing",
  },
  {
    id: "v2-index-claim-fact",
    label: "Claim / Fact",
    boundary: "backend/app/knowledge/claims/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/claims/AGENTS.md · CLAUDE.md",
    description:
      "Promotes ExtractedClaim to SupportedClaim and VerifiedFact only through evidence and applicable validation.",
    guarantee:
      "Conflicts are linked and retained; no unsupported assertion is promoted to a verified fact.",
    kind: "safety",
    variant: "processing",
  },
  {
    id: "v2-index-kg-build",
    label: "KG Build",
    boundary: "backend/app/knowledge/graph/",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context: "backend/app/knowledge/graph/AGENTS.md · CLAUDE.md",
    description:
      "Projects canonical entities, relations, events, temporals, claims, facts, conflicts, and exact evidence into Neo4j.",
    guarantee:
      "Canonical graph writes are workspace- and generation-bound and cannot be overwritten by lower-precedence extraction.",
    kind: "storage",
    variant: "graphrag",
  },
  {
    id: "v2-index-bm25",
    label: "BM25",
    boundary: "backend/app/retrieval/indexing.py",
    documentation: "docs/architecture/retrieval-boundaries.md",
    context: "backend/app/retrieval/AGENTS.md",
    description:
      "Builds the generation-scoped workspace BM25 corpus and evidence metadata projection.",
    guarantee:
      "Sparse readiness is credited only when output and source fingerprints match the candidate generation.",
    kind: "storage",
    variant: "dense",
  },
  {
    id: "v2-index-dense",
    label: "Dense / Qdrant",
    boundary: "backend/app/retrieval/qdrant.py",
    documentation: "docs/architecture/retrieval-boundaries.md",
    context: "backend/app/retrieval/AGENTS.md",
    description:
      "Embeds snapshot chunks and writes deterministic, generation-bearing points to shared Qdrant collections.",
    guarantee:
      "Workspace filters, embedding configuration compatibility, dimensions, and generation fingerprints are mandatory.",
    kind: "storage",
    variant: "dense",
  },
  {
    id: "v2-index-graphrag",
    label: "GraphRAG",
    boundary: "backend/app/graphrag/",
    documentation: "docs/architecture/graphrag-boundary.md",
    context: "backend/app/graphrag/AGENTS.md · CLAUDE.md",
    description:
      "Builds the Microsoft GraphRAG extracted-knowledge projection and its Local, Global, and DRIFT artifacts.",
    guarantee:
      "This extracted projection remains separate from canonical KG Build and is bound to the same candidate generation.",
    kind: "storage",
    variant: "graphrag",
  },
  {
    id: "v2-index-readiness",
    label: "Generation / Readiness",
    boundary:
      "backend/app/knowledge/construction.py · backend/app/query/cutover.py · backend/app/workflows/knowledge.py",
    documentation: "docs/architecture/query-v2/knowledge-construction.md",
    context:
      "backend/app/knowledge/AGENTS.md · backend/app/workflows/AGENTS.md",
    description:
      "Tracks exact-generation projection readiness, detached infrastructure and curation checks, acceptance evaluation, and the atomic workspace runtime pointer.",
    guarantee:
      "A failed, partial, stale, mixed-generation, curation-changing, or sub-threshold attempt is audited and cannot change the live runtime.",
    kind: "safety",
    variant: "delivery",
  },
];

export const SYSTEM_MAP_V2_MANIFEST: Record<
  "query" | "indexing",
  SystemMapSubsystem[]
> = {
  query: QUERY_V2_SUBSYSTEMS,
  indexing: INDEXING_V2_SUBSYSTEMS,
};

const MANIFEST_GROUP_WIDTH = MAP_NODE_WIDTH + MAP_GROUP_HORIZONTAL_PADDING * 2;
const MANIFEST_GROUP_HEIGHT =
  MAP_NODE_MIN_HEIGHT + MAP_GROUP_VERTICAL_PADDING * 2;
const MANIFEST_GROUP_GAP = 24;

function manifestMap(boundaries: SystemMapSubsystem[]): {
  nodes: MapNode[];
  edges: Edge[];
} {
  const nodes = boundaries.map((subsystem, index) => {
    const groupX = index * (MANIFEST_GROUP_WIDTH + MANIFEST_GROUP_GAP);
    const item = node(
      subsystem.id,
      groupX + MAP_GROUP_HORIZONTAL_PADDING,
      MAP_GROUP_VERTICAL_PADDING,
      subsystem.label,
      subsystem.description,
      subsystem.boundary,
      subsystem.guarantee,
    );
    return {
      ...item,
      data: {
        ...item.data,
        kind: subsystem.kind,
        layer: subsystem.boundary,
        documentation: subsystem.documentation,
        context: subsystem.context,
      },
    };
  });
  return { nodes, edges: [] };
}

function manifestFlowGroups(tab: "ingestion" | "query"): FlowGroupNode[] {
  const boundaries =
    tab === "query" ? QUERY_V2_SUBSYSTEMS : INDEXING_V2_SUBSYSTEMS;
  return boundaries.map((subsystem, index) => ({
    id: "flow-group-" + tab + "-" + subsystem.id,
    type: "flow-group",
    position: { x: index * (MANIFEST_GROUP_WIDTH + MANIFEST_GROUP_GAP), y: 0 },
    data: {
      label: subsystem.label,
      variant: subsystem.variant,
      boundary: subsystem.boundary,
      documentation: subsystem.documentation,
      context: subsystem.context,
    },
    draggable: false,
    selectable: false,
    focusable: false,
    style: {
      height: MANIFEST_GROUP_HEIGHT,
      pointerEvents: "none",
      width: MANIFEST_GROUP_WIDTH,
      zIndex: -1,
    },
  }));
}

function connectManifest(source: string, target: string, label?: string): Edge {
  return links([source, target, label])[0];
}

staticMaps.query = manifestMap(QUERY_V2_SUBSYSTEMS);
staticMaps.query.edges = [
  connectManifest("v2-query-conversation-context", "v2-query-understanding"),
  connectManifest("v2-query-understanding", "v2-query-ir"),
  connectManifest("v2-query-ir", "v2-query-execution-planning"),
  connectManifest(
    "v2-query-execution-planning",
    "v2-query-structured",
    "planned step",
  ),
  connectManifest(
    "v2-query-execution-planning",
    "v2-query-knowledge-graph",
    "planned step",
  ),
  connectManifest(
    "v2-query-execution-planning",
    "v2-query-retrieval",
    "planned step",
  ),
  connectManifest(
    "v2-query-execution-planning",
    "v2-query-graphrag",
    "planned capability",
  ),
  connectManifest(
    "v2-query-structured",
    "v2-query-result-evidence",
    "EngineResult",
  ),
  connectManifest(
    "v2-query-knowledge-graph",
    "v2-query-result-evidence",
    "EngineResult",
  ),
  connectManifest(
    "v2-query-retrieval",
    "v2-query-result-evidence",
    "EngineResult",
  ),
  connectManifest(
    "v2-query-graphrag",
    "v2-query-result-evidence",
    "typed finding",
  ),
  connectManifest(
    "v2-query-result-evidence",
    "v2-query-reasoning",
    "ReasoningPackage",
  ),
  connectManifest("v2-query-reasoning", "v2-query-answer", "grounded artifact"),
];

staticMaps.ingestion = manifestMap(INDEXING_V2_SUBSYSTEMS);
staticMaps.ingestion.edges = [
  connectManifest("v2-index-source", "v2-index-document-structure"),
  connectManifest("v2-index-document-structure", "v2-index-entity-mention"),
  connectManifest("v2-index-entity-mention", "v2-index-identity"),
  connectManifest("v2-index-identity", "v2-index-relation"),
  connectManifest("v2-index-relation", "v2-index-event"),
  connectManifest("v2-index-event", "v2-index-temporal"),
  connectManifest("v2-index-temporal", "v2-index-claim-fact"),
  connectManifest("v2-index-claim-fact", "v2-index-kg-build"),
  connectManifest("v2-index-kg-build", "v2-index-bm25", "projection"),
  connectManifest("v2-index-kg-build", "v2-index-dense", "projection"),
  connectManifest(
    "v2-index-kg-build",
    "v2-index-graphrag",
    "separate projection",
  ),
  connectManifest("v2-index-bm25", "v2-index-readiness", "ready"),
  connectManifest("v2-index-dense", "v2-index-readiness", "ready"),
  connectManifest("v2-index-graphrag", "v2-index-readiness", "ready"),
];

function mapNodePosition(id: string, x: number, y: number) {
  const workflowPositions: Record<string, { x: number; y: number }> = {
    state: { x: 1145, y: 160 },
    "lock-decision": { x: 1145, y: 500 },
    checkpoint: { x: 2060, y: 300 },
    "retry-decision": { x: 2060, y: 40 },
    cancel: { x: 2060, y: 540 },
    sse: { x: 2565, y: 300 },
  };
  return workflowPositions[id] ?? { x, y };
}

function recordKind(interfaces: string): RecordKind | undefined {
  if (/Qdrant/i.test(interfaces)) return "vector";
  if (/cache/i.test(interfaces)) return "cache";
  if (/Filesystem|Parquet|JSON/i.test(interfaces)) return "file";
  if (/SQLite|workflow_runs|QueryRun persistence/i.test(interfaces))
    return "database";
  return undefined;
}

function node(
  id: string,
  x: number,
  y: number,
  label: string,
  description: string,
  interfaces: string,
  guarantee: string,
): MapNode {
  const presentation = nodePresentation(id);
  return {
    id,
    type: "architecture",
    position: mapNodePosition(id, x, y),
    data: {
      label,
      description,
      interfaces,
      guarantee,
      ...presentation,
      recordKind:
        presentation.kind === "storage" ? recordKind(interfaces) : undefined,
    },
    style: { minHeight: MAP_NODE_MIN_HEIGHT, width: MAP_NODE_WIDTH, zIndex: 2 },
  };
}
function links(...pairs: [string, string, string?][]): Edge[] {
  return pairs.map(([source, target, label]) => ({
    id: `${source}-${target}`,
    source,
    target,
    label,
    animated: true,
    style: { stroke: "var(--cortex-secondary)", strokeWidth: 1.5 },
    zIndex: 1,
    labelStyle: { fill: "var(--cortex-text)", fontSize: 10, fontWeight: 750 },
    labelBgPadding: [5, 3],
    labelBgBorderRadius: 4,
    labelBgStyle: {
      fill: "var(--cortex-panel)",
      fillOpacity: 0.98,
      stroke: "var(--cortex-line)",
      strokeWidth: 1,
    },
  }));
}
function nodePresentation(
  id: string,
): Pick<MapNodeData, "kind" | "layer" | "model"> {
  const values: Record<
    string,
    Pick<MapNodeData, "kind" | "layer" | "model">
  > = {
    frontend: { kind: "input", layer: "User interface" },
    backend: { kind: "service", layer: "Command and query API" },
    worker: { kind: "worker", layer: "Background execution" },
    sqlite: { kind: "storage", layer: "Relational persistence" },
    redis: { kind: "service", layer: "Broker" },
    qdrant: { kind: "storage", layer: "Vector persistence" },
    neo4j: { kind: "storage", layer: "Knowledge graph persistence" },
    ollama: { kind: "llm-local", layer: "Local provider" },
    graphrag: { kind: "worker", layer: "GraphRAG execution" },
    openai: { kind: "llm-api", layer: "API provider" },
    anthropic: { kind: "llm-api", layer: "API provider" },
    recovery: { kind: "safety", layer: "Workflow recovery" },
    reconciliation: { kind: "safety", layer: "Orphan reconciliation" },
    ui: { kind: "input", layer: "User interface" },
    api: { kind: "service", layer: "Command boundary" },
    definition: { kind: "service", layer: "Workflow definition" },
    state: { kind: "storage", layer: "Durable state" },
    "lock-decision": { kind: "decision", layer: "Concurrency" },
    "workflow-redis": { kind: "service", layer: "Broker" },
    "workflow-worker": { kind: "worker", layer: "Background execution" },
    checkpoint: { kind: "storage", layer: "Durability" },
    "retry-decision": { kind: "decision", layer: "Recovery" },
    cancel: { kind: "safety", layer: "Cancellation and recovery" },
    sse: { kind: "delivery", layer: "Live delivery" },
  };
  return values[id] ?? { kind: "service", layer: "V2 subsystem" };
}

function ArchitectureNode({ data, selected }: NodeProps<MapNode>) {
  return (
    <article
      className={`architecture-node is-${data.kind}${selected ? " is-selected" : ""}`}
    >
      <Handle type="target" position={Position.Left} />
      <span className="architecture-node__layer">
        {nodeCategoryLabels[data.kind]}
      </span>
      <strong>{data.label}</strong>
      {data.recordKind && (
        <span
          className={`architecture-node__persistence is-${data.recordKind}`}
        >
          {
            (
              {
                database: "Veritabanı",
                file: "Dosya kaydı",
                vector: "Vektör deposu",
                cache: "İndeks cache",
              } as Record<RecordKind, string>
            )[data.recordKind]
          }
        </span>
      )}
      {data.kind === "decision" && (
        <span className="architecture-node__decision">Karar noktası</span>
      )}
      {data.model && (
        <span className={`architecture-node__model-type is-${data.kind}`}>
          {data.kind === "llm-local"
            ? "LLM · Local"
            : data.kind === "llm-api"
              ? "LLM · API"
              : "Model · Local"}
        </span>
      )}
      <small>{data.description}</small>
      <Handle type="source" position={Position.Right} />
    </article>
  );
}

function FlowGroup({ data }: NodeProps<FlowGroupNode>) {
  return (
    <section className={`flow-group is-${data.variant}`}>
      <span>{data.label}</span>
    </section>
  );
}

const nodeTypes: NodeTypes = {
  architecture: ArchitectureNode,
  "flow-group": FlowGroup,
};

function flowGroups(tab: MapTab): FlowGroupNode[] {
  if (tab === "ingestion" || tab === "query") return manifestFlowGroups(tab);
  const groups: Record<
    MapTab,
    Array<[string, number, number, number, number, FlowGroupVariant]>
  > = {
    system: [
      [
        "Cortex platform services",
        -MAP_GROUP_HORIZONTAL_PADDING,
        -MAP_GROUP_VERTICAL_PADDING,
        1105,
        1300,
        "platform",
      ],
    ],
    ingestion: [
      ["Giriş ve doğrulama", -100, -40, 1320, 1100, "input"],
      ["Belge işleme ve kalıcı kayıt", 1300, -40, 4065, 1100, "processing"],
      ["Dayanıklı ingestion", 5465, -40, 1320, 1280, "durable"],
      ["Dense indeksleme", 6885, -80, 1015, 580, "dense"],
      ["GraphRAG ve canonical knowledge", 6885, 600, 2850, 600, "graphrag"],
    ],
    query: [
      ["İstek ve planlama", -100, -60, 1340, 1000, "input"],
      [
        "Normal QA, GraphRAG ve verified aggregation",
        1340,
        -60,
        2235,
        1260,
        "query",
      ],
      ["Kanıt, citation ve yanıt", 3675, -60, 1625, 1000, "delivery"],
    ],
    workflows: [
      ["Komut ve tanım", -100, -40, 1045, 900, "input"],
      ["Durable orchestration", 1045, -40, 1320, 900, "durable"],
      ["İlerleme teslimi", 2465, -40, 405, 900, "delivery"],
    ],
  };
  return groups[tab].map(([label, x, y, width, height, variant], index) => ({
    id: `flow-group-${tab}-${index}`,
    type: "flow-group",
    position: { x, y },
    data: { label, variant },
    draggable: false,
    selectable: false,
    focusable: false,
    style: { height, pointerEvents: "none", width, zIndex: -1 },
  }));
}

function nodeWidth(node: MapNode) {
  return typeof node.style?.width === "number"
    ? node.style.width
    : MAP_NODE_WIDTH;
}

function nodeHeight(node: MapNode) {
  return typeof node.style?.minHeight === "number"
    ? node.style.minHeight
    : MAP_NODE_MIN_HEIGHT;
}

function groupWidth(group: FlowGroupNode) {
  return typeof group.style?.width === "number" ? group.style.width : 0;
}

function groupHeight(group: FlowGroupNode) {
  return typeof group.style?.height === "number" ? group.style.height : 0;
}

function assertMapLayout(
  tab: MapTab,
  nodes: MapNode[],
  groups: FlowGroupNode[],
) {
  for (const node of nodes) {
    const width = nodeWidth(node);
    const height = nodeHeight(node);
    const containingGroups = groups.filter(
      (group) =>
        node.position.x >= group.position.x + MAP_GROUP_HORIZONTAL_PADDING &&
        node.position.y >= group.position.y + MAP_GROUP_VERTICAL_PADDING &&
        node.position.x + width <=
          group.position.x + groupWidth(group) - MAP_GROUP_HORIZONTAL_PADDING &&
        node.position.y + height <=
          group.position.y + groupHeight(group) - MAP_GROUP_VERTICAL_PADDING,
    );
    if (containingGroups.length !== 1)
      throw new Error(
        `${tab}: ${node.id} must be inside exactly one padded group`,
      );
  }

  for (let index = 0; index < nodes.length; index += 1) {
    for (
      let candidateIndex = index + 1;
      candidateIndex < nodes.length;
      candidateIndex += 1
    ) {
      const current = nodes[index];
      const candidate = nodes[candidateIndex];
      const separatedHorizontally =
        current.position.x + nodeWidth(current) + MAP_NODE_HORIZONTAL_GAP <=
          candidate.position.x ||
        candidate.position.x + nodeWidth(candidate) + MAP_NODE_HORIZONTAL_GAP <=
          current.position.x;
      const separatedVertically =
        current.position.y + nodeHeight(current) + MAP_NODE_VERTICAL_GAP <=
          candidate.position.y ||
        candidate.position.y + nodeHeight(candidate) + MAP_NODE_VERTICAL_GAP <=
          current.position.y;
      if (!separatedHorizontally && !separatedVertically)
        throw new Error(
          `${tab}: ${current.id} and ${candidate.id} violate the layout gap`,
        );
    }
  }
}

const detailTabs: DetailTab[] = [
  "description",
  "interfaces",
  "guarantee",
  "documentation",
  "context",
];

const detailTabLabels: Record<DetailTab, string> = {
  description: "Açıklama",
  interfaces: "Sınır",
  guarantee: "Garanti",
  documentation: "Doküman",
  context: "AI context",
};

function selectedDetail(selected: MapNode | undefined, detailTab: DetailTab) {
  if (!selected) return "";
  if (detailTab === "description") return selected.data.description;
  if (detailTab === "interfaces") return selected.data.interfaces;
  if (detailTab === "guarantee") return selected.data.guarantee;
  if (detailTab === "documentation")
    return (
      selected.data.documentation ??
      "Bu bileşenin kanonik dokümanı sistem haritası indeksinde kayıtlıdır."
    );
  return (
    selected.data.context ??
    "Bu bileşen en yakın üst AGENTS.md bağlamını kullanır."
  );
}

export function ASystemMap() {
  const [services, setServices] = useState<Record<string, string>>({
    backend: "unknown",
  });
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [activeTab, setActiveTab] = useState<MapTab>("system");
  const [selectedId, setSelectedId] = useState("backend");
  const [detailTab, setDetailTab] = useState<DetailTab>("description");
  const [detailsOpen, setDetailsOpen] = useState(false);
  useEffect(() => {
    const refresh = () =>
      Promise.all([apiClient.getHealth(), apiClient.diagnostics()])
        .then(([health, diagnostics]) =>
          setServices({
            ...health.services,
            recovery: diagnostics.workflows.interrupted
              ? "attention"
              : "healthy",
            reconciliation: diagnostics.reconciliation.state,
          }),
        )
        .catch(() => setServices({ backend: "unavailable" }));
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    void apiClient
      .getSettings()
      .then(({ settings: values }) => setSettings(values))
      .catch(() => undefined);
  }, []);
  const systemMap = useMemo(
    () => ({
      nodes: [
        ["frontend", "healthy"],
        ...Object.entries(services).filter(([id]) => id !== "frontend"),
      ].map(
        ([id, status], index): MapNode => ({
          ...node(
            id,
            (index % 3) * 320,
            Math.floor(index / 3) *
              (MAP_NODE_MIN_HEIGHT + MAP_NODE_VERTICAL_GAP),
            `${id.replaceAll("_", " ")} · ${status}`,
            serviceDescription(id),
            serviceInterface(id),
            serviceGuarantee(id),
          ),
          style: {
            minHeight: MAP_NODE_MIN_HEIGHT,
            width: MAP_NODE_WIDTH,
            zIndex: 2,
          },
        }),
      ),
      edges: links(
        ["frontend", "backend"],
        ["backend", "sqlite"],
        ["backend", "redis"],
        ["backend", "qdrant"],
        ["backend", "ollama"],
        ["redis", "worker"],
        ["worker", "qdrant"],
        ["worker", "graphrag"],
      ),
    }),
    [services],
  );
  const baseMap = activeTab === "system" ? systemMap : staticMaps[activeTab];
  const map = useMemo(
    () => ({
      ...baseMap,
      nodes: baseMap.nodes.map((item) => ({
        ...item,
        data: {
          ...item.data,
          model: modelLabel(item.id, item.data.model, settings),
        },
      })),
    }),
    [baseMap, settings],
  );
  const selected =
    map.nodes.find((item) => item.id === selectedId) ?? map.nodes[0];
  const mapNodes = useMemo(() => {
    const groups = flowGroups(activeTab);
    assertMapLayout(activeTab, map.nodes, groups);
    return [...groups, ...map.nodes];
  }, [activeTab, map.nodes]);
  const selectTab = (tab: MapTab) => {
    setActiveTab(tab);
    setSelectedId(
      (tab === "system" ? systemMap : staticMaps[tab]).nodes[0]?.id ?? "",
    );
    setDetailTab("description");
    setDetailsOpen(false);
  };
  const visibleEdges = map.edges.filter(
    (edge) =>
      map.nodes.some((item) => item.id === edge.source) &&
      map.nodes.some((item) => item.id === edge.target),
  );
  return (
    <section className="system-map page-stack">
      <ATabs
        className="system-map__tabs"
        aria-label="Sistem haritası görünümleri"
      >
        {(Object.keys(tabLabels) as MapTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "is-active" : undefined}
            onClick={() => selectTab(tab)}
          >
            {tabLabels[tab]}
          </button>
        ))}
      </ATabs>
      <div className="system-map__legend" aria-label="Düğüm renkleri lejantı">
        {legendGroups.map((group) => (
          <section key={group.label} className="system-map__legend-group">
            <strong>{group.label}</strong>
            <div>
              {group.items.map((item) => (
                <span
                  key={item.kind}
                  className={`system-map__legend-item is-${item.kind}`}
                >
                  <i aria-hidden="true" />
                  {item.label}
                </span>
              ))}
            </div>
          </section>
        ))}
      </div>
      <div
        className={`system-map__layout${detailsOpen ? " is-detail-open" : ""}`}
      >
        <ACard title={tabLabels[activeTab]}>
          <AFlowCanvas
            nodes={mapNodes}
            edges={visibleEdges}
            nodeTypes={nodeTypes}
            onNodeClick={(id) => {
              setSelectedId(id);
              setDetailTab("description");
              setDetailsOpen(true);
            }}
            height={620}
            showMiniMap
          />
        </ACard>
        <aside className="system-map__sidebar" aria-hidden={!detailsOpen}>
          <div className="system-map__sidebar-header">
            <div>
              <span>Seçili bileşen</span>
              <h2 className="text-lg">{selected?.data.label}</h2>
            </div>
            <button
              type="button"
              className="system-map__sidebar-close"
              aria-label="Seçili bileşen ayrıntılarını kapat"
              onClick={() => setDetailsOpen(false)}
            >
              ×
            </button>
          </div>
          <ATabs
            className="system-map__detail-tabs"
            aria-label="Bileşen ayrıntıları"
          >
            {detailTabs.map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={detailTab === tab}
                className={detailTab === tab ? "is-active" : undefined}
                onClick={() => setDetailTab(tab)}
              >
                {detailTabLabels[tab]}
              </button>
            ))}
          </ATabs>
          {detailTab === "description" && selected?.data.model && (
            <div className="system-map__model-detail">
              <strong>
                {selected.data.kind === "llm-local"
                  ? "LLM · Local"
                  : selected.data.kind === "llm-api"
                    ? "LLM · API"
                    : "Yerel model"}
              </strong>
              <span>{selected.data.model}</span>
              <p>{modelDescription(selected.data.kind, selected.data.model)}</p>
            </div>
          )}
          <p>{selectedDetail(selected, detailTab)}</p>
        </aside>
      </div>
      <AInfoPanel title="Runtime architecture manifest">
        {activeTab === "query"
          ? "Query V2 groups are implemented subsystem boundaries. Execution Planning owns engine work; Structured Query, Knowledge Graph, Retrieval, and GraphRAG converge only through Result & Evidence. Phase 13 still owns runtime activation."
          : activeTab === "ingestion"
            ? "Indexing V2 follows one candidate generation from source processing through canonical KG construction and the separate BM25, Dense/Qdrant, and GraphRAG projections. Generation / Readiness is the fail-closed activation gate."
            : "Every node describes a real runtime boundary. Select a node to inspect its interface, guarantee, canonical documentation, and scoped AI-development context."}
      </AInfoPanel>
    </section>
  );
}

function serviceDescription(id: string) {
  return (
    (
      {
        frontend: "React/Vite kullanıcı arayüzü.",
        backend: "FastAPI komut ve sorgu sınırı.",
        worker: "Dramatiq tabanlı kalıcı iş yürütücüsü.",
        sqlite:
          "İlişkisel kayıt teknolojisi: workspace, belge, durum ve telemetry için SQLite.",
        redis: "Dramatiq broker ve iş teslimi.",
        qdrant:
          "Vektör kayıt teknolojisi: workspace filtreli dense retrieval için Qdrant Vector DB.",
        neo4j:
          "Query V2 persistent knowledge graph; workspace-scoped extracted ve canonical katmanlar.",
        ollama: "Yerel embedding ve model sağlayıcısı.",
        graphrag:
          "Worker-owned GraphRAG extracted-knowledge producer; native çıktılar Parquet/JSON dosyalarıdır.",
        openai: "İsteğe bağlı OpenAI sağlayıcı bağlantısı.",
        anthropic: "İsteğe bağlı Anthropic sağlayıcı bağlantısı.",
        recovery: "Kesilmiş workflow kurtarma durumu.",
        reconciliation: "Orphan kaynak uzlaştırma durumu.",
      } as Record<string, string>
    )[id] ?? "Cortex servis bileşeni."
  );
}
function serviceInterface(id: string) {
  return (
    (
      {
        frontend: "Browser → /api proxy",
        backend: "REST + SSE",
        worker: "Dramatiq actors",
        sqlite: "SQLAlchemy 2 + WAL",
        redis: "Redis 7 broker",
        qdrant: "Qdrant client",
        neo4j: "Neo4j Bolt driver",
        ollama: "Ollama HTTP API",
        graphrag: "Microsoft GraphRAG CLI",
      } as Record<string, string>
    )[id] ?? "Health ve tanılama API’si"
  );
}
function serviceGuarantee(id: string) {
  return (
    (
      {
        sqlite: "Tüm workspace-scoped kayıtlar workspace_id taşır.",
        qdrant: "Tüm sorgu ve silmeler workspace payload filtresi içerir.",
        worker: "Workflow adımları idempotent ve checkpoint tabanlıdır.",
        backend: "Hatalar sanitize edilmiş Cortex envelope ile döner.",
        frontend: "Uzun süren iş ilerlemesi yeniden bağlanabilir.",
        graphrag: "Kanonik graph bilgisi ayrı workspace kökünde saklanır.",
      } as Record<string, string>
    )[id] ?? "Canlı durum backend health kontrolünden yenilenir."
  );
}
function modelLabel(
  id: string,
  fallback: string | undefined,
  settings: Record<string, unknown>,
) {
  if (id === "embedding") return providerModel(settings, "embedding");
  if (id === "metadata") return providerModel(settings, "metadata");
  if (id === "answer") return providerModel(settings, "answer");
  if (id === "router") return providerModel(settings, "router");
  return fallback;
}
function providerModel(settings: Record<string, unknown>, layer: string) {
  const provider = String(settings[`${layer}_provider`] ?? "ollama");
  const model = String(settings[`${layer}_model`] ?? "configured model");
  return `${provider} · ${model} · ${provider === "ollama" ? "Local" : "API"}`;
}
function modelDescription(kind: NodeKind, model: string) {
  if (kind === "llm-local")
    return `${model} bu makinede Ollama veya yerel model adaptörü üzerinden çalışır; içerik harici bir sağlayıcıya gönderilmez.`;
  if (kind === "llm-api")
    return `${model} yapılandırılmış sağlayıcının API’si üzerinden çağrılır; sağlayıcı ve model ayarları Ayarlar ekranından gelir.`;
  return `${model} retrieval adaylarını yerel olarak yeniden sıralamak için kullanılır.`;
}
