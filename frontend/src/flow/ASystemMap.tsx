import { Handle, Position, type Edge, type Node, type NodeProps, type NodeTypes } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../api/client";
import { ACard, AInfo, ATabs } from "../components/ui";
import { AFlowCanvas } from "./AFlowCanvas";

type MapTab = "system" | "ingestion" | "query" | "workflows";
type DetailTab = "description" | "interfaces" | "guarantee";
type NodeKind = "input" | "service" | "processor" | "decision" | "storage" | "retrieval" | "llm-local" | "llm-api" | "safety" | "worker" | "delivery";
type MapNodeData = { label: string; description: string; interfaces: string; guarantee: string; kind: NodeKind; layer: string; model?: string };
type MapNode = Node<MapNodeData, "architecture">;

const tabLabels: Record<MapTab, string> = {
  system: "Canlı sistem",
  ingestion: "Belge akışı",
  query: "Sorgu akışı",
  workflows: "Dayanıklı işler",
};

const staticMaps: Record<Exclude<MapTab, "system">, { nodes: MapNode[]; edges: Edge[] }> = {
  ingestion: {
    nodes: [
      node("upload", 0, 160, "Yükleme", "PDF, DOCX, Markdown ve metin kabul edilir.", "POST /workspaces/{id}/uploads", "Dosya boyutu ve biçimi doğrulanır."),
      node("docling", 230, 160, "Docling normalizasyonu", "Kaynak dosya Markdown çalışma kopyasına dönüştürülür.", "İç ayrıştırıcı sınırı", "Orijinal kaynak saklanır."),
      node("chunks", 460, 160, "Parçalama ve metadata", "Normalize içerik bağımsız parçalara ayrılır.", "SQLite: documents, versions, chunks", "Parça ve GraphRAG text unit ayrı tutulur."),
      node("embedding", 690, 55, "Embedding üretimi", "Embedding sağlayıcısı ile retrieval vektörleri hazırlanır.", "Embedding adapter", "Yapılandırma parmak izi uyumsuzsa dense indeks korunur."),
      node("workflow", 690, 160, "İndeksleme işi", "Kalıcı ingestion workflow arka planda yürür.", "REST komutu → Dramatiq", "Adımlar idempotent ve yeniden denenebilir."),
      node("qdrant", 920, 70, "Hibrit arama indeksi", "Yoğun vektörler, bm25s ve reranker için kaynak.", "Qdrant + workspace_id filtresi", "Her sorgu workspace filtresi taşır."),
      node("graphrag", 920, 255, "Microsoft GraphRAG", "Workspace-izole graph indeksleme ve Local/Global/DRIFT yolları.", "Worker-owned CLI adapter", "GraphRAG bilgi modeli kanoniktir."),
      node("sqlite", 1140, 160, "SQLite durum kaydı", "Belge sürümleri, indeks durumu ve workflow checkpoint’leri.", "SQLAlchemy + WAL", "İş durumu sayfa değişiminden bağımsızdır."),
    ],
    edges: links(["upload", "docling"], ["docling", "chunks"], ["chunks", "embedding"], ["chunks", "workflow"], ["embedding", "qdrant"], ["workflow", "graphrag"], ["workflow", "sqlite"]),
  },
  query: {
    nodes: [
      node("chat", 0, 170, "Sohbet isteği", "Workspace ve konuşma kapsamındaki kullanıcı sorusu.", "POST /conversations/{id}/messages", "Konuşma sınırı korunur."),
      node("router", 230, 170, "LlamaIndex Router", "Sorgu için uygun retrieval yolunu seçer.", "CustomQueryEngine adapters", "Yollar ayrı kalır; uygunsuz birleşim yapılmaz."),
      node("hybrid", 480, 55, "Hibrit arama", "Qdrant dense, bm25s fusion ve yerel BGE reranker.", "Qdrant + bm25s", "Embedding yapılandırması uyumsuzsa dense arama engellenir."),
      node("graph", 480, 285, "GraphRAG yolları", "Local, Global ve DRIFT bağımsız query engine’lerdir.", "GraphRAG adapter", "Stale graph grounded cevap olarak sunulmaz."),
      node("evidence", 740, 170, "Kanıt normalizasyonu", "Kaynaklar ortak Cortex evidence modeline dönüştürülür.", "Workspace-scoped source nodes", "Faktüel iddialar citation gerektirir."),
      node("answer", 980, 170, "Grounded yanıt", "Sentez, inference etiketi ve kaynak ayrıntıları.", "OpenAI Responses / provider adapter", "Desteksiz yanıtta citation yoktur."),
      node("history", 1210, 170, "Konuşma ve telemetry", "Mesajlar, query run, gecikme ve maliyet kalıcı kaydedilir.", "SQLite", "Kullanıcı mesajları düzenlenebilir, yanıt geçmişi korunur."),
    ],
    edges: links(["chat", "router"], ["router", "hybrid"], ["router", "graph"], ["hybrid", "evidence"], ["graph", "evidence"], ["evidence", "answer"], ["answer", "history"]),
  },
  workflows: {
    nodes: [
      node("ui", 0, 160, "Cortex arayüzü", "Yükleme, silme, reindex ve kurtarma komutları.", "REST commands", "İşler gezinmeden sonra da sürer."),
      node("api", 240, 160, "FastAPI", "Komutu doğrular, kalıcı run ve step kayıtlarını oluşturur.", "/api/v1/workflows", "Hatalar standardize edilmiş envelope döner."),
      node("state", 480, 55, "SQLite workflow state", "Run, adım, olay, lock ve recovery state saklanır.", "workflow_runs / workflow_step_runs", "Safe checkpoint’ten retry yapılır."),
      node("redis", 480, 285, "Redis + Dramatiq", "İş teslimi ve worker çalıştırma sınırı.", "Dramatiq broker", "API yeniden başlasa bile run kaydı korunur."),
      node("worker", 740, 170, "Worker", "Ingestion, reindex, GraphRAG ve bakım workflow’larını yürütür.", "Versioned definitions", "Workspace lock tehlikeli eşzamanlılığı önler."),
      node("sse", 1000, 170, "SSE olay akışı", "UI canlı ilerlemeyi izler; bağlantı kesilince geçmişten geri yükler.", "GET /workflows/{id}/events", "Yalnızca gerçekleşen aşamalar gösterilir."),
    ],
    edges: links(["ui", "api"], ["api", "state"], ["api", "redis"], ["state", "worker"], ["redis", "worker"], ["worker", "sse"], ["sse", "ui"]),
  },
};

function node(id: string, x: number, y: number, label: string, description: string, interfaces: string, guarantee: string): MapNode {
  return { id, type: "architecture", position: { x, y }, data: { label, description, interfaces, guarantee, ...nodePresentation(id) }, style: { width: 205, borderWidth: 0 } };
}
function links(...pairs: [string, string][]): Edge[] { return pairs.map(([source, target]) => ({ id: `${source}-${target}`, source, target, animated: true })); }
function healthy(status: string) { return status === "healthy" || status === "configured"; }

function nodePresentation(id: string): Pick<MapNodeData, "kind" | "layer" | "model"> {
  const values: Record<string, Pick<MapNodeData, "kind" | "layer" | "model">> = {
    upload: { kind: "input", layer: "Kullanıcı girişi" }, docling: { kind: "processor", layer: "Belge işleme" }, chunks: { kind: "processor", layer: "Belge işleme" }, embedding: { kind: "llm-local", layer: "Embedding", model: "Embedding modeli · Local" }, workflow: { kind: "worker", layer: "Orkestrasyon" }, qdrant: { kind: "storage", layer: "Retrieval" }, graphrag: { kind: "llm-api", layer: "Graph indeksleme", model: "GraphRAG provider · API" }, sqlite: { kind: "storage", layer: "Kalıcı durum" },
    chat: { kind: "input", layer: "İstek" }, router: { kind: "decision", layer: "Yönlendirme" }, hybrid: { kind: "retrieval", layer: "Hibrit retrieval", model: "BGE reranker · Local" }, graph: { kind: "retrieval", layer: "GraphRAG retrieval" }, evidence: { kind: "safety", layer: "Kanıt güvenliği" }, answer: { kind: "llm-api", layer: "Yanıt sentezi", model: "Yanıt modeli · API" }, history: { kind: "storage", layer: "Kalıcı durum" },
    ui: { kind: "input", layer: "Kullanıcı arayüzü" }, api: { kind: "service", layer: "Komut sınırı" }, state: { kind: "storage", layer: "Kalıcı durum" }, redis: { kind: "service", layer: "Broker" }, worker: { kind: "worker", layer: "Arka plan" }, sse: { kind: "delivery", layer: "Canlı teslim" },
  };
  return values[id] ?? { kind: "service", layer: "Platform" };
}

function ArchitectureNode({ data, selected }: NodeProps<MapNode>) {
  return <article className={`architecture-node is-${data.kind}${selected ? " is-selected" : ""}`}>
    <Handle type="target" position={Position.Left} />
    <span className="architecture-node__layer">{data.layer}</span>
    <strong>{data.label}</strong>
    {data.kind === "decision" && <span className="architecture-node__decision">Karar noktası</span>}
    {data.model && <span className="architecture-node__model">{data.model}</span>}
    <small>{data.description}</small>
    <Handle type="source" position={Position.Right} />
  </article>;
}

const nodeTypes: NodeTypes = { architecture: ArchitectureNode };

export function ASystemMap() {
  const [services, setServices] = useState<Record<string, string>>({ backend: "unknown" });
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [activeTab, setActiveTab] = useState<MapTab>("system");
  const [selectedId, setSelectedId] = useState("backend");
  const [detailTab, setDetailTab] = useState<DetailTab>("description");
  useEffect(() => {
    const refresh = () => Promise.all([apiClient.getHealth(), apiClient.diagnostics()]).then(([health, diagnostics]) => setServices({ ...health.services, recovery: diagnostics.workflows.interrupted ? "attention" : "healthy", reconciliation: diagnostics.reconciliation.state })).catch(() => setServices({ backend: "unavailable" }));
    void refresh(); const timer = window.setInterval(() => void refresh(), 15_000); return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { void apiClient.getSettings().then(({ settings: values }) => setSettings(values)).catch(() => undefined); }, []);
  const systemMap = useMemo(() => ({
    nodes: Object.entries(services).map(([id, status], index): MapNode => ({
      ...node(id, (index % 3) * 240, Math.floor(index / 3) * 135, `${id.replaceAll("_", " ")} · ${status}`, serviceDescription(id), serviceInterface(id), serviceGuarantee(id)),
      style: { width: 190, borderColor: healthy(status) ? "#16a34a" : status === "unavailable" ? "#dc2626" : "#ca8a04", borderWidth: 2 },
    })),
    edges: links(["frontend", "backend"], ["backend", "sqlite"], ["backend", "redis"], ["backend", "qdrant"], ["backend", "ollama"], ["redis", "worker"], ["worker", "qdrant"], ["worker", "graphrag"]),
  }), [services]);
  const baseMap = activeTab === "system" ? systemMap : staticMaps[activeTab];
  const map = useMemo(() => ({
    ...baseMap,
    nodes: baseMap.nodes.map((item) => ({
      ...item,
      data: { ...item.data, model: modelLabel(item.id, item.data.model, settings) },
    })),
  }), [baseMap, settings]);
  const selected = map.nodes.find((item) => item.id === selectedId) ?? map.nodes[0];
  const selectTab = (tab: MapTab) => { setActiveTab(tab); setSelectedId((tab === "system" ? systemMap : staticMaps[tab]).nodes[0]?.id ?? ""); setDetailTab("description"); };
  const visibleEdges = map.edges.filter((edge) => map.nodes.some((item) => item.id === edge.source) && map.nodes.some((item) => item.id === edge.target));
  return <section className="system-map page-stack">
    <header className="page-hero"><div><p className="eyebrow">Yaşayan mimari</p><h1>Sistem haritası</h1><p>Canlı servis durumu ile Cortex’ün uygulanan veri ve iş akışı sınırlarını birlikte gösterir.</p></div></header>
    <ATabs className="system-map__tabs" aria-label="Sistem haritası görünümleri">{(Object.keys(tabLabels) as MapTab[]).map((tab) => <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? "is-active" : undefined} onClick={() => selectTab(tab)}>{tabLabels[tab]}</button>)}</ATabs>
    <div className="system-map__layout"><ACard title={tabLabels[activeTab]}><AFlowCanvas nodes={map.nodes} edges={visibleEdges} nodeTypes={nodeTypes} onNodeClick={(id) => { setSelectedId(id); setDetailTab("description"); }} height={620} showMiniMap /></ACard><ACard title="Seçili bileşen"><h2 className="text-lg">{selected?.data.label}</h2><ATabs className="system-map__detail-tabs" aria-label="Bileşen ayrıntıları">{(["description", "interfaces", "guarantee"] as DetailTab[]).map((tab) => <button key={tab} type="button" role="tab" aria-selected={detailTab === tab} className={detailTab === tab ? "is-active" : undefined} onClick={() => setDetailTab(tab)}>{({ description: "Açıklama", interfaces: "Arayüz", guarantee: "Garanti" } as Record<DetailTab, string>)[tab]}</button>)}</ATabs><p>{detailTab === "description" ? selected?.data.description : detailTab === "interfaces" ? selected?.data.interfaces : selected?.data.guarantee}</p></ACard></div>
    <AInfo title="Okuma biçimi">Yeşil düğümler canlı sağlık kontrolünden gelir. Belge, sorgu ve workflow sekmeleri ise V1’de uygulanan mimari sınırları gösterir.</AInfo>
  </section>;
}

function serviceDescription(id: string) { return ({ frontend: "React/Vite kullanıcı arayüzü.", backend: "FastAPI komut ve sorgu sınırı.", worker: "Dramatiq tabanlı kalıcı iş yürütücüsü.", sqlite: "Workspace, belge, durum ve telemetry veritabanı.", redis: "Dramatiq broker ve iş teslimi.", qdrant: "Workspace filtreli yoğun retrieval depolama.", ollama: "Yerel embedding ve model sağlayıcısı.", graphrag: "Worker-owned GraphRAG bağımlılığı.", openai: "İsteğe bağlı OpenAI sağlayıcı bağlantısı.", anthropic: "İsteğe bağlı Anthropic sağlayıcı bağlantısı.", recovery: "Kesilmiş workflow kurtarma durumu.", reconciliation: "Orphan kaynak uzlaştırma durumu." } as Record<string, string>)[id] ?? "Cortex servis bileşeni."; }
function serviceInterface(id: string) { return ({ frontend: "Browser → /api proxy", backend: "REST + SSE", worker: "Dramatiq actors", sqlite: "SQLAlchemy 2 + WAL", redis: "Redis 7 broker", qdrant: "Qdrant client", ollama: "Ollama HTTP API", graphrag: "Microsoft GraphRAG CLI" } as Record<string, string>)[id] ?? "Health ve tanılama API’si"; }
function serviceGuarantee(id: string) { return ({ sqlite: "Tüm workspace-scoped kayıtlar workspace_id taşır.", qdrant: "Tüm sorgu ve silmeler workspace payload filtresi içerir.", worker: "Workflow adımları idempotent ve checkpoint tabanlıdır.", backend: "Hatalar sanitize edilmiş Cortex envelope ile döner.", frontend: "Uzun süren iş ilerlemesi yeniden bağlanabilir.", graphrag: "Kanonik graph bilgisi ayrı workspace kökünde saklanır." } as Record<string, string>)[id] ?? "Canlı durum backend health kontrolünden yenilenir."; }
function modelLabel(id: string, fallback: string | undefined, settings: Record<string, unknown>) {
  if (id === "embedding") return providerModel(settings, "embedding");
  if (id === "answer") return providerModel(settings, "answer");
  if (id === "router") return providerModel(settings, "router");
  return fallback;
}
function providerModel(settings: Record<string, unknown>, layer: string) {
  const provider = String(settings[`${layer}_provider`] ?? "ollama");
  const model = String(settings[`${layer}_model`] ?? "configured model");
  return `${provider} · ${model} · ${provider === "ollama" ? "Local" : "API"}`;
}
