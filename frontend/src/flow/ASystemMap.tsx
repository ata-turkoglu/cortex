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
      node("upload", 0, 360, "Yükleme", "PDF, DOCX, Markdown ve metin kabul edilir.", "POST /workspaces/{id}/uploads", "Dosya boyutu ve biçimi doğrulanır."),
      node("upload-validation", 320, 360, "Dosya doğrulama", "Biçim, boyut ve workspace kapsamı denetlenir.", "Upload validation boundary", "Geçersiz içerik workflow başlatmaz."),
      node("duplicate-decision", 640, 360, "Sürüm kararı", "Aynı belge için yeni sürüm veya reddetme yolu seçilir.", "Document/version lookup", "Önceki sürümün kaynak kaydı korunur."),
      node("rejected", 960, 610, "Reddedilen yükleme", "Doğrulama veya sürüm kuralını geçemeyen istek.", "API error envelope", "İndeks ve kalıcı çalışma kaydı oluşturulmaz."),
      node("source-store", 960, 220, "Kaynak kaydı", "Orijinal dosya ve belge sürümü kalıcı olarak kaydedilir.", "SQLite documents + versions", "Orijinal kaynak değişmeden saklanır."),
      node("docling", 1280, 220, "Docling normalizasyonu", "Kaynak dosya Markdown çalışma kopyasına dönüştürülür.", "İç ayrıştırıcı sınırı", "Orijinal kaynak saklanır."),
      node("normalization-decision", 1600, 220, "İçerik yeterli mi?", "Ayrıştırma sonucu indekslemeye uygunluk açısından kontrol edilir.", "Normalized document contract", "Boş veya hatalı içerik retrieval’a geçmez."),
      node("chunks", 1920, 220, "Parçalama ve metadata", "Normalize içerik bağımsız parçalara ayrılır.", "SQLite: documents, versions, chunks", "Parça ve GraphRAG text unit ayrı tutulur."),
      node("metadata", 2240, 40, "Metadata zenginleştirme", "Başlık, özet ve arama metadata’sı gerektiğinde model ile üretilir.", "Metadata provider adapter", "Belge metni workspace sınırını aşmaz."),
      node("embedding", 2240, 250, "Embedding üretimi", "Embedding sağlayıcısı ile retrieval vektörleri hazırlanır.", "Embedding adapter", "Yapılandırma parmak izi uyumsuzsa dense indeks korunur."),
      node("workflow", 2240, 470, "İndeksleme işi", "Kalıcı ingestion workflow arka planda yürür.", "REST komutu → Dramatiq", "Adımlar idempotent ve yeniden denenebilir."),
      node("qdrant", 2560, 250, "Yoğun vektör indeksi", "Embedding’ler workspace filtresiyle Qdrant’a yazılır.", "Qdrant + workspace_id filtresi", "Her sorgu workspace filtresi taşır."),
      node("sparse-index", 2560, 470, "Seyrek indeks", "bm25s arama verisi workspace için hazırlanır.", "bm25s workspace index", "Dense ve sparse indeksler ayrı yaşam döngüsüne sahiptir."),
      node("graph-decision", 2560, 40, "GraphRAG etkin mi?", "Graph indeksleme yalnızca hazır ve etkin workspace’lerde devam eder.", "Workspace GraphRAG state", "Hazır olmayan graph grounded cevap üretmez."),
      node("graphrag", 2880, 40, "Microsoft GraphRAG", "Workspace-izole graph indeksleme ve Local/Global/DRIFT yolları.", "Worker-owned CLI adapter", "GraphRAG bilgi modeli kanoniktir."),
      node("sqlite", 2880, 470, "SQLite durum kaydı", "Belge sürümleri, indeks durumu ve workflow checkpoint’leri.", "SQLAlchemy + WAL", "İş durumu sayfa değişiminden bağımsızdır."),
    ],
    edges: links(["upload", "upload-validation"], ["upload-validation", "duplicate-decision"], ["upload-validation", "rejected", "geçersiz"], ["duplicate-decision", "source-store", "yeni sürüm"], ["duplicate-decision", "rejected", "reddet"], ["source-store", "docling"], ["docling", "normalization-decision"], ["normalization-decision", "chunks", "uygun"], ["normalization-decision", "rejected", "yetersiz"], ["chunks", "metadata"], ["chunks", "embedding"], ["chunks", "workflow"], ["metadata", "workflow"], ["embedding", "qdrant"], ["workflow", "sparse-index"], ["workflow", "graph-decision"], ["workflow", "sqlite"], ["graph-decision", "graphrag", "etkin"], ["graph-decision", "sqlite", "pas geç"]),
  },
  query: {
    nodes: [
      node("chat", 0, 360, "Sohbet isteği", "Workspace ve konuşma kapsamındaki kullanıcı sorusu.", "POST /conversations/{id}/messages", "Konuşma sınırı korunur."),
      node("conversation-context", 320, 360, "Konuşma bağlamı", "İzinli konuşma geçmişi ve workspace kapsamı hazırlanır.", "Conversation persistence", "Başka workspace’in geçmişi okunmaz."),
      node("router", 640, 360, "Sorgu planı", "Router, sorgu için retrieval yaklaşımını seçer.", "CustomQueryEngine adapters", "Yollar ayrı kalır; uygunsuz birleşim yapılmaz."),
      node("hybrid", 960, 80, "Hibrit yol", "Dense, sparse, fusion ve reranking aşamalarını başlatır.", "Qdrant + bm25s", "Embedding uyumsuzsa dense arama engellenir."),
      node("dense", 1280, 20, "Dense retrieval", "Qdrant benzerlik araması workspace filtresiyle çalışır.", "Qdrant vector query", "Sadece aynı workspace adayları döner."),
      node("sparse", 1280, 230, "Sparse retrieval", "bm25s terim araması aynı workspace indeksinde çalışır.", "bm25s workspace index", "Dense arızasında kısmi sonuç sağlayabilir."),
      node("fusion", 1600, 125, "RRF fusion", "Dense ve sparse adayları reciprocal-rank fusion ile birleştirilir.", "Hybrid retrieval contract", "Aday kaynakları korunur."),
      node("reranker", 1920, 125, "Yerel BGE reranker", "Birleşen adaylar yerel modelle yeniden sıralanır.", "Local reranker adapter", "Model yoksa sonuçlar açık kısmi modda döner."),
      node("graph-ready", 960, 570, "Graph hazır mı?", "Graph state, indeks güncelliği ve sorgu kipini denetler.", "GraphRAG workspace state", "Stale graph grounded cevap olarak sunulmaz."),
      node("graph-local", 1280, 470, "Graph Local", "Varlık merkezli GraphRAG sorgusu.", "GraphRAG Local engine", "Kanonik graph verisi kullanılır."),
      node("graph-global", 1280, 670, "Graph Global", "Topluluk özetleri üzerinde GraphRAG sorgusu.", "GraphRAG Global engine", "Kanonik graph verisi kullanılır."),
      node("graph-drift", 1600, 570, "Graph DRIFT", "Yerel ve global kanıtı harmanlayan GraphRAG modu.", "GraphRAG DRIFT engine", "Modele sunulan kanıt ayrı normalize edilir."),
      node("evidence", 2240, 360, "Kanıt normalizasyonu", "Kaynaklar ortak Cortex evidence modeline dönüştürülür.", "Workspace-scoped source nodes", "Faktüel iddialar citation gerektirir."),
      node("citation-check", 2560, 360, "Citation kontrolü", "Kaynak eşleşmesi ve kanıt bulunurluğu doğrulanır.", "Evidence validation", "Desteksiz iddia grounded olarak işaretlenmez."),
      node("answer", 2880, 360, "Grounded yanıt", "Sentez, inference etiketi ve kaynak ayrıntıları.", "Provider answer adapter", "Desteksiz yanıtta citation yoktur."),
      node("answer-state", 3200, 360, "Yanıt durumu", "Yanıt, citation ve çalışma telemetry’si birlikte kaydedilir.", "Query run persistence", "Kullanıcı mesajları düzenlenebilir, yanıt geçmişi korunur."),
      node("history", 3520, 360, "Konuşma ve telemetry", "Mesajlar, query run, gecikme ve maliyet kalıcı kaydedilir.", "SQLite", "Geçmiş sayfa değişiminden bağımsızdır."),
    ],
    edges: links(["chat", "conversation-context"], ["conversation-context", "router"], ["router", "hybrid", "hybrid"], ["router", "graph-ready", "graph"], ["hybrid", "dense"], ["hybrid", "sparse"], ["dense", "fusion"], ["sparse", "fusion"], ["fusion", "reranker"], ["reranker", "evidence"], ["graph-ready", "graph-local", "local"], ["graph-ready", "graph-global", "global"], ["graph-local", "graph-drift"], ["graph-global", "graph-drift"], ["graph-drift", "evidence"], ["graph-ready", "hybrid", "hazır değil"], ["evidence", "citation-check"], ["citation-check", "answer", "kanıtlı"], ["citation-check", "answer-state", "eksik citation"], ["answer", "answer-state"], ["answer-state", "history"]),
  },
  workflows: {
    nodes: [
      node("ui", 0, 360, "Cortex arayüzü", "Yükleme, silme, reindex ve kurtarma komutları.", "REST commands", "İşler gezinmeden sonra da sürer."),
      node("api", 320, 360, "FastAPI komutu", "Komutu doğrular, kalıcı run ve step kayıtlarını oluşturur.", "/api/v1/workflows", "Hatalar standardize edilmiş envelope döner."),
      node("definition", 640, 360, "Sürümlü workflow tanımı", "Komutun izinli adımları ve retry sınırları seçilir.", "Versioned definitions", "Uygulanan adımlar kayıtlı tanımla tutarlıdır."),
      node("state", 960, 160, "Kalıcı run kaydı", "Run, adım, olay, lock ve recovery state saklanır.", "workflow_runs / workflow_step_runs", "Safe checkpoint’ten retry yapılır."),
      node("lock-decision", 960, 500, "Workspace lock uygun mu?", "Tehlikeli eşzamanlı komutlar için workspace kilidi kontrol edilir.", "Workspace lock record", "Çakışan mutasyonlar aynı anda yürütülmez."),
      node("redis", 1280, 500, "Redis + Dramatiq", "İş teslimi ve worker çalıştırma sınırı.", "Dramatiq broker", "API yeniden başlasa bile run kaydı korunur."),
      node("worker", 1600, 500, "Worker", "Ingestion, reindex, GraphRAG ve bakım workflow’larını yürütür.", "Versioned definitions", "Yan etkili adımlar idempotent tasarlanır."),
      node("checkpoint", 1920, 300, "Atomik checkpoint", "Başarılı adım sonucu ve sonraki adım atomik kaydedilir.", "Step run + checkpoint", "Yeniden deneme güvenli noktadan başlar."),
      node("retry-decision", 2240, 160, "Retry gerekli mi?", "Hata, retry politikası ve iptal sinyali değerlendirilir.", "Recovery policy", "Terminal hata görünür şekilde kalıcıdır."),
      node("cancel", 2240, 500, "İptal / recovery komutu", "Kullanıcı iptali veya kesilmiş run kurtarma isteği.", "REST recovery command", "İptal checkpoint sınırında uygulanır."),
      node("sse", 2560, 300, "SSE olay akışı", "UI canlı ilerlemeyi izler; bağlantı kesilince geçmişten geri yükler.", "GET /workflows/{id}/events", "Yalnızca gerçekleşen aşamalar gösterilir."),
    ],
    edges: links(["ui", "api"], ["api", "definition"], ["definition", "state"], ["definition", "lock-decision"], ["lock-decision", "redis", "kilit alındı"], ["lock-decision", "state", "çakışma"], ["redis", "worker"], ["worker", "checkpoint"], ["checkpoint", "retry-decision"], ["retry-decision", "worker", "devam"], ["retry-decision", "sse", "tamamlandı"], ["retry-decision", "cancel", "iptal / hata"], ["cancel", "state"], ["checkpoint", "state"], ["state", "sse"], ["sse", "ui"]),
  },
};

function node(id: string, x: number, y: number, label: string, description: string, interfaces: string, guarantee: string): MapNode {
  return { id, type: "architecture", position: { x, y }, data: { label, description, interfaces, guarantee, ...nodePresentation(id) }, style: { width: 205, borderWidth: 0 } };
}
function links(...pairs: [string, string, string?][]): Edge[] { return pairs.map(([source, target, label]) => ({ id: `${source}-${target}`, source, target, label, animated: true, style: { stroke: "#71839b", strokeWidth: 1.5 }, labelStyle: { fill: "#60708b", fontSize: 11, fontWeight: 650 }, labelBgStyle: { fill: "#f8fafc", fillOpacity: 0.92 } })); }
function healthy(status: string) { return status === "healthy" || status === "configured"; }

function nodePresentation(id: string): Pick<MapNodeData, "kind" | "layer" | "model"> {
  const values: Record<string, Pick<MapNodeData, "kind" | "layer" | "model">> = {
    upload: { kind: "input", layer: "Kullanıcı girişi" }, "upload-validation": { kind: "safety", layer: "Yükleme güvenliği" }, "duplicate-decision": { kind: "decision", layer: "Sürümleme" }, rejected: { kind: "safety", layer: "Reddedilen istek" }, "source-store": { kind: "storage", layer: "Belge kaydı" }, docling: { kind: "processor", layer: "Belge işleme" }, "normalization-decision": { kind: "decision", layer: "İçerik kalitesi" }, chunks: { kind: "processor", layer: "Belge işleme" }, metadata: { kind: "llm-api", layer: "Metadata", model: "Metadata modeli · API" }, embedding: { kind: "llm-local", layer: "Embedding", model: "Embedding modeli · Local" }, workflow: { kind: "worker", layer: "Orkestrasyon" }, qdrant: { kind: "storage", layer: "Dense retrieval" }, "sparse-index": { kind: "storage", layer: "Sparse retrieval" }, "graph-decision": { kind: "decision", layer: "GraphRAG koşulu" }, graphrag: { kind: "llm-api", layer: "Graph indeksleme", model: "GraphRAG provider · API" }, sqlite: { kind: "storage", layer: "Kalıcı durum" },
    chat: { kind: "input", layer: "İstek" }, "conversation-context": { kind: "processor", layer: "Konuşma kapsamı" }, router: { kind: "decision", layer: "Sorgu planı" }, hybrid: { kind: "retrieval", layer: "Hibrit retrieval" }, dense: { kind: "retrieval", layer: "Dense retrieval" }, sparse: { kind: "retrieval", layer: "Sparse retrieval" }, fusion: { kind: "processor", layer: "Aday birleştirme" }, reranker: { kind: "llm-local", layer: "Reranking", model: "BGE reranker · Local" }, "graph-ready": { kind: "decision", layer: "GraphRAG koşulu" }, "graph-local": { kind: "retrieval", layer: "GraphRAG Local" }, "graph-global": { kind: "retrieval", layer: "GraphRAG Global" }, "graph-drift": { kind: "retrieval", layer: "GraphRAG DRIFT" }, evidence: { kind: "safety", layer: "Kanıt güvenliği" }, "citation-check": { kind: "decision", layer: "Citation kontrolü" }, answer: { kind: "llm-api", layer: "Yanıt sentezi", model: "Yanıt modeli · API" }, "answer-state": { kind: "storage", layer: "Query telemetry" }, history: { kind: "storage", layer: "Kalıcı durum" },
    ui: { kind: "input", layer: "Kullanıcı arayüzü" }, api: { kind: "service", layer: "Komut sınırı" }, definition: { kind: "service", layer: "Workflow tanımı" }, state: { kind: "storage", layer: "Kalıcı durum" }, "lock-decision": { kind: "decision", layer: "Eşzamanlılık" }, redis: { kind: "service", layer: "Broker" }, worker: { kind: "worker", layer: "Arka plan" }, checkpoint: { kind: "storage", layer: "Dayanıklılık" }, "retry-decision": { kind: "decision", layer: "Recovery" }, cancel: { kind: "safety", layer: "İptal ve recovery" }, sse: { kind: "delivery", layer: "Canlı teslim" },
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
    nodes: [["frontend", "healthy"], ...Object.entries(services).filter(([id]) => id !== "frontend")].map(([id, status], index): MapNode => ({
      ...node(id, (index % 3) * 320, Math.floor(index / 3) * 190, `${id.replaceAll("_", " ")} · ${status}`, serviceDescription(id), serviceInterface(id), serviceGuarantee(id)),
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
