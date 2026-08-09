import { Handle, Position, type Edge, type Node, type NodeProps, type NodeTypes } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../api/client";
import { ACard, AInfoPanel, ATabs } from "../components/ui";
import { AFlowCanvas } from "./AFlowCanvas";

type MapTab = "system" | "ingestion" | "query" | "workflows";
type DetailTab = "description" | "interfaces" | "guarantee";
type NodeKind = "input" | "service" | "processor" | "decision" | "storage" | "retrieval" | "llm-local" | "llm-api" | "safety" | "worker" | "delivery";
type MapNodeData = { label: string; description: string; interfaces: string; guarantee: string; kind: NodeKind; layer: string; model?: string };
type MapNode = Node<MapNodeData, "architecture">;
type FlowGroupNode = Node<{ label: string }, "flow-group">;

const legendGroups: Array<{ label: string; items: Array<{ kind: NodeKind; label: string }> }> = [
  { label: "Uygulama akışı", items: [{ kind: "input", label: "Girdi" }, { kind: "processor", label: "İşleme" }, { kind: "worker", label: "Arka plan" }, { kind: "delivery", label: "Teslim" }] },
  { label: "Veri ve retrieval", items: [{ kind: "storage", label: "Kalıcı veri" }, { kind: "retrieval", label: "Retrieval" }] },
  { label: "Kontrol", items: [{ kind: "decision", label: "Karar" }, { kind: "safety", label: "Güvenlik" }] },
  { label: "LLM kaynağı", items: [{ kind: "llm-local", label: "Local" }, { kind: "llm-api", label: "API" }] },
  { label: "Platform", items: [{ kind: "service", label: "Servis" }] },
];

const tabLabels: Record<MapTab, string> = {
  system: "Canlı sistem",
  ingestion: "Belge akışı",
  query: "Sorgu akışı",
  workflows: "Arka plan işlemleri",
};

const detailedNodePresentation: Record<string, Pick<MapNodeData, "kind" | "layer" | "model">> = {
  "upload-request": { kind: "input", layer: "Kullanıcı girişi" }, "workspace-scope": { kind: "safety", layer: "Workspace güvenliği" }, "folder-resolution": { kind: "safety", layer: "Workspace güvenliği" }, "replacement-decision": { kind: "decision", layer: "Sürümleme" }, "file-read": { kind: "processor", layer: "Yükleme hazırlığı" }, "upload-validation": { kind: "safety", layer: "Yükleme güvenliği" }, "source-hash": { kind: "processor", layer: "İçerik kimliği" }, "content-duplicate": { kind: "decision", layer: "Tekrar denetimi" }, rejected: { kind: "safety", layer: "Reddedilen istek" }, "source-store": { kind: "storage", layer: "Kaynak depolama" }, "text-source-decision": { kind: "decision", layer: "Belge işleme" }, "direct-text-read": { kind: "processor", layer: "Belge işleme" }, docling: { kind: "processor", layer: "Belge işleme" }, normalized: { kind: "storage", layer: "Normalize kaynak kaydı" }, "document-record": { kind: "storage", layer: "Kalıcı belge kaydı" }, "version-record": { kind: "storage", layer: "Kalıcı belge kaydı" }, "system-metadata": { kind: "storage", layer: "Kalıcı belge kaydı" }, chunks: { kind: "storage", layer: "Kalıcı chunk kaydı" }, relationships: { kind: "storage", layer: "Belge ilişkileri" }, workflow: { kind: "storage", layer: "Kalıcı workflow kaydı" }, "dispatch-decision": { kind: "decision", layer: "İş teslimi" }, "ingestion-worker": { kind: "worker", layer: "Arka plan" }, "checkpoint-parse": { kind: "storage", layer: "Dayanıklı checkpoint" }, "checkpoint-normalize": { kind: "storage", layer: "Dayanıklı checkpoint" }, "checkpoint-chunk": { kind: "storage", layer: "Dayanıklı checkpoint" }, "checkpoint-index": { kind: "storage", layer: "Dayanıklı checkpoint" },
};
detailedNodePresentation["logical-documents"] = {
  kind: "processor",
  layer: "Mantıksal belge algılama",
};
detailedNodePresentation["checkpoint-logical"] = {
  kind: "storage",
  layer: "Dayanıklı checkpoint",
};
const ingestionNodesKey: string = "nodes";
const ingestionEdgesKey: string = "edges";

function graphragConfigurationNodes(): MapNode[] { return [
  node("community-detection", 6600, 420, "Community detection", "Graph communities are detected algorithmically from the graph; no LLM model is selected for this step.", "Microsoft GraphRAG clustering", "Community membership is distinct from report generation."),
  node("claims-optional", 6900, 560, "Optional claim extraction", "Claim extraction is disabled by default and runs only when the user enables it in GraphRAG settings.", "GraphRAG extract_claims", "Disabled settings create no claim-extraction model call."),
  node("community-reports", 6900, 700, "Community report generation", "Reports use the user-selected community provider and model.", "GraphRAG community_reports", "The selected model is recorded with GraphRAG stage usage."),
]; }

function importantIndexingNodes(): MapNode[] { return [
  node("index-state", 5700, 320, "İndeks durumu · SQLite", "Belge ingestion tamamlandıktan sonra workspace indeks durumları SQLite’ta ayrı yaşam döngülerinde izlenir.", "SQLite · workspace_index_states / graphrag_states", "İndeks türleri birbirinden bağımsız olarak hazır veya reindex gerekli olabilir."),
  node("dense-trigger", 6000, 80, "Dense reindex gerekli mi?", "Embedding yapılandırması değiştiğinde ya da kullanıcı reindex istediğinde ayrı run planlanır.", "Embedding configuration fingerprint", "Aktif vektörler yeni indeks hazır olmadan değiştirilmez."),
  node("dense-reindex", 6300, 80, "Dense reindex workflow", "clear vectors, embed, upsert ve activate adımlarını ayrı durable run yürütür.", "dense_reindex", "Workspace index lock ile çakışan dense reindex engellenir."),
  node("qdrant-index", 6600, 80, "Qdrant dense vektörleri", "Workspace filtreli aktif dense vektörler Qdrant vector DB’de saklanır.", "Qdrant Vector DB · chunks collection", "Farklı embedding yapılandırmaları aynı aktif alanı paylaşmaz."),
  node("sparse-index", 6000, 320, "bm25s sparse corpus", "Workspace’e özel sparse corpus ve evidence metadata’sı dosya tabanlı cache’de saklanır.", "Filesystem · workspace cache path", "Sparse indeksler workspace’ler arasında paylaşılmaz."),
  node("graphrag-trigger", 6000, 560, "GraphRAG tetikleyicisi", "Manual veya threshold ayarı GraphRAG reindex isteğini belirler.", "GraphRAG workspace state", "Graph güncel değilse grounded cevap olarak kullanılmaz."),
  node("graphrag-reindex", 6300, 560, "GraphRAG reindex workflow", "snapshot, materialize, index ve mirror adımlarını ayrı durable run yürütür.", "graphrag_reindex", "Workspace graph lock ile çakışan graph işlemleri engellenir."),
  node("graphrag-artifacts", 6600, 560, "GraphRAG çalışma verisi", "Kanonik GraphRAG çıktıları workspace dosya alanında Parquet/JSON olarak saklanır; vektörleri Qdrant’a aynalanır.", "Filesystem · GraphRAG root; Qdrant vector mirror", "Local, Global ve DRIFT sorgu yolları bu veriyi kullanır."),
]; }
const importantIndexingEdges: Edge[] = links(["checkpoint-index", "index-state", "ingestion tamamlandı"], ["index-state", "dense-trigger", "ayrı tetikleyici"], ["dense-trigger", "dense-reindex", "reindex gerekirse"], ["dense-reindex", "qdrant-index"], ["index-state", "sparse-index", "workspace corpus"], ["index-state", "graphrag-trigger", "manual / threshold"], ["graphrag-trigger", "graphrag-reindex", "ayrı tetikleyici"], ["graphrag-reindex", "graphrag-artifacts"]);
importantIndexingEdges.push(
  ...links(
    ["graphrag-reindex", "community-detection"],
    ["graphrag-reindex", "claims-optional", "enabled only"],
    ["community-detection", "community-reports"],
    ["community-reports", "graphrag-artifacts"],
    ["claims-optional", "graphrag-artifacts"],
  ),
);

const importantIndexingPresentation: Record<string, Pick<MapNodeData, "kind" | "layer" | "model">> = {
  "index-state": { kind: "storage", layer: "İndeks yaşam döngüsü" }, "dense-trigger": { kind: "decision", layer: "Dense reindex" }, "dense-reindex": { kind: "worker", layer: "Ayrı workflow" }, "qdrant-index": { kind: "storage", layer: "Dense retrieval" }, "sparse-index": { kind: "storage", layer: "Sparse retrieval" }, "graphrag-trigger": { kind: "decision", layer: "GraphRAG reindex" }, "graphrag-reindex": { kind: "worker", layer: "Ayrı workflow" }, "graphrag-artifacts": { kind: "storage", layer: "GraphRAG çalışma verisi" },
};

const detailedIngestionMap: { nodes: MapNode[]; edges: Edge[] } = {
  nodes: [
    node("upload-request", 0, 360, "Yükleme isteği", "İstemci bir veya daha fazla kaynak dosya gönderir.", "POST /workspaces/{id}/uploads", "İstek workspace kapsamında işlenir."),
    node("workspace-scope", 300, 360, "Workspace kapsamı", "Workspace varlığı ve kaynak dizinleri yükleme öncesi çözümlenir.", "WorkspaceContext", "Dosyalar yalnızca ilgili workspace köküne yazılır."),
    node("folder-resolution", 600, 360, "Klasör çözümleme", "İsteğe bağlı klasör yolu workspace içinde doğrulanır.", "Folder resolver", "Geçersiz klasör kalıcı yazımdan önce durur."),
    node("replacement-decision", 900, 360, "Replacement isteği mi?", "replace_document_id varsa tek dosya ve aynı workspace belgesi aranır.", "Document lookup", "Geçersiz replacement kalıcı yazımdan önce durur."),
    node("file-read", 1200, 200, "Dosyayı güvenli okuma", "İçerik, üst sınırdan bir bayt fazla okunarak boyut korumasına alınır.", "Upload byte guard", "Sınırı aşan dosya saklanmaz."),
    node("upload-validation", 1500, 200, "Biçim ve boyut doğrulama", "İzinli uzantı, MIME türü ve dosya boyutu denetlenir.", "Upload validation boundary", "Geçersiz içerik workflow başlatmaz."),
    node("source-hash", 1800, 200, "Kaynak hash’i", "Dosya içeriğinin SHA-256 özeti hesaplanır.", "SHA-256", "Tekrar denetimi içerik üzerinden yapılır."),
    node("content-duplicate", 2100, 200, "Aynı içerik var mı?", "Aynı workspace’te eşleşen source hash aranır.", "DocumentVersion lookup", "Özdeş içerik ikinci kez indekslenmez."),
    node("rejected", 2400, 620, "Reddedilen yükleme", "Geçersiz, tekrar veya ayrıştırılamayan içerik için standart API hatası döner.", "API error envelope", "Belge, chunk veya workflow kaydı oluşturulmaz."),
    node("source-store", 2400, 200, "Kaynak dosya kaydı · Disk", "Doğrulanan dosya workspace’in uploads alanına yazılır.", "Filesystem · workspace/uploads", "Kaynak dosya değişmeden korunur."),
    node("text-source-decision", 2700, 200, "Düz metin kaynağı mı?", "Dosya uzantısı .md veya .txt ise doğrudan okuma yolu seçilir.", "Filename extension", "Markdown ve metin kaynakları Docling/OCR’a gönderilmez."),
    node("docling", 3000, 80, "Docling ayrıştırma", "PDF ve DOCX kaynakları Markdown’a çevrilir; DOCX Word Heading 2 stilleri tam olarak ## başlıklarına normalize edilir.", "İç ayrıştırıcı sınırı", "Ayrıştırma hatası 422 ile sonlanır."),
    node("direct-text-read", 3000, 360, "Doğrudan UTF-8 okuma", "Markdown ve metin, içerik korunarak doğrudan okunur.", "UTF-8 text reader", "Geçersiz UTF-8 içerik 422 ile sonlanır."),
    node("normalized", 3300, 200, "Normalize Markdown · Disk", "Satır sonları normalize edilir ve çalışma kopyası workspace’in normalized alanına kaydedilir.", "Filesystem · workspace/normalized", "Dosya işlemi açık SQLite transaction dışında yapılır."),
    node("document-record", 3600, 80, "Belge kaydı · SQLite", "Yeni belge oluşturulur veya replacement belgesi SQLite’a yazılır.", "SQLite · documents", "Belge her zaman workspace kapsamındadır."),
    node("version-record", 3600, 320, "Sürüm kaydı · SQLite", "Kaynak/normalize yol ve içerik hash’leriyle belge sürümü SQLite’a yazılır.", "SQLite · document_versions", "Önceki sürümler korunur."),
    node("system-metadata", 3900, 80, "Sistem metadata’sı · SQLite", "Dosya adı, MIME türü, hash, boyut ve model ataması SQLite’ta kaydedilir.", "SQLite · document_metadata", "Kullanıcı düzeltmesi sistem metadata’sından önceliklidir."),
    node("logical-documents", 3900, 560, "Heading 2 → mantıksal belgeler · SQLite", "Her Markdown ## başlığı yeni bir mantıksal belge başlatır; başlık metni önek veya arşiv kodu yorumu yapılmadan kod ve başlık olarak kaydedilir.", "SQLite · logical_documents", "Yalnızca Heading 2 sınırdır; chunk ve GraphRAG girdileri mantıksal belgeye bağlanır."),
    node("chunks", 3900, 320, "Chunk kayıtları · SQLite", "Normalize içerik token sınırı ve overlap ile parçalara ayrılır ve SQLite’a yazılır.", "SQLite · chunks", "Her chunk workspace ve belge sürümü kapsamını taşır."),
    node("relationships", 4200, 320, "Chunk komşulukları · SQLite", "Sıralı chunk’lar için next ilişkileri SQLite’ta kalıcılaştırılır.", "SQLite · chunk_relationships", "Komşuluk yalnızca aynı belge sürümünde kurulur."),
    node("workflow", 4500, 320, "Ingestion run · SQLite", "Kalıcı ingestion run ve payload SQLite’a yazılır.", "SQLite · workflow_runs", "Broker kesintisinde run queued kalır."),
    node("dispatch-decision", 4800, 320, "Broker erişilebilir mi?", "Dramatiq actor’a gönderim denenir; hata upload sonucunu bozmaz.", "Redis / Dramatiq", "Kalıcı run daha sonra yeniden teslim edilebilir."),
    node("ingestion-worker", 5100, 320, "Ingestion worker", "Yükleme sırasında tamamlanan adımları ve indeks adımını dayanıklı checkpoint’lerle izler.", "Document ingestion v1", "İptal ve yeniden deneme güvenli adım sınırlarında uygulanır."),
    node("checkpoint-parse", 5400, 80, "Parse checkpoint · SQLite", "Yükleme sırasında tamamlanan parse adımının SQLite kaydı.", "SQLite · workflow_step_runs", "Adım tekrarlandığında checkpoint korunur."),
    node("checkpoint-normalize", 5400, 240, "Normalize checkpoint · SQLite", "Yükleme sırasında tamamlanan normalize adımının SQLite kaydı.", "SQLite · workflow_step_runs", "Restart sonrası tamamlanan adım yeniden çalışmaz."),
    node("checkpoint-logical", 5400, 320, "Mantıksal belge checkpoint · SQLite", "Algılanan belge sınırları ve metadata nesneleri chunking öncesinde kalıcılaştırılır.", "SQLite · workflow_step_runs", "Belge sınırları yeniden denemede aynı sonucu üretir."),
    node("checkpoint-chunk", 5400, 400, "Chunk checkpoint · SQLite", "Yükleme sırasında tamamlanan chunk adımının SQLite kaydı.", "SQLite · workflow_step_runs", "İlerleme SSE üzerinden yayımlanır."),
    node("checkpoint-index", 5400, 560, "Index checkpoint · SQLite", "İndeks adımı SQLite’ta kalıcı olay ve checkpoint ile tamamlanır.", "SQLite · workflow_step_runs", "Run tamamlandığında retention politikasına girer."),
    ...importantIndexingNodes(),
    ...graphragConfigurationNodes(),
  ],
  edges: [...links(["upload-request", "workspace-scope"], ["workspace-scope", "folder-resolution"], ["folder-resolution", "replacement-decision"], ["replacement-decision", "file-read", "uygun"], ["replacement-decision", "rejected", "geçersiz"], ["file-read", "upload-validation"], ["upload-validation", "source-hash"], ["upload-validation", "rejected", "geçersiz"], ["source-hash", "content-duplicate"], ["content-duplicate", "source-store", "yeni içerik"], ["content-duplicate", "rejected", "tekrar"], ["source-store", "text-source-decision"], ["text-source-decision", "docling", "PDF / DOCX"], ["text-source-decision", "direct-text-read", "MD / TXT"], ["docling", "normalized"], ["docling", "rejected", "ayrıştırılamadı"], ["direct-text-read", "normalized"], ["direct-text-read", "rejected", "geçersiz UTF-8"], ["normalized", "document-record"], ["document-record", "version-record"], ["version-record", "system-metadata"], ["version-record", "chunks"], ["chunks", "relationships"], ["relationships", "workflow"], ["workflow", "dispatch-decision"], ["dispatch-decision", "ingestion-worker", "gönderildi"], ["dispatch-decision", "workflow", "queued"], ["ingestion-worker", "checkpoint-parse"], ["checkpoint-parse", "checkpoint-normalize"], ["checkpoint-normalize", "checkpoint-chunk"], ["checkpoint-chunk", "checkpoint-index"]), ...importantIndexingEdges],
};

detailedIngestionMap.edges = detailedIngestionMap.edges.filter(
  (edge) =>
    edge.id !== "version-record-chunks" &&
    edge.id !== "checkpoint-normalize-checkpoint-chunk",
);
detailedIngestionMap.edges.push(
  ...links(
    ["version-record", "logical-documents", "yalnızca ## sınırları"],
    ["logical-documents", "chunks", "ayrı chunk kümeleri"],
    ["checkpoint-normalize", "checkpoint-logical"],
    ["checkpoint-logical", "checkpoint-chunk"],
  ),
);

const staticMaps: Record<Exclude<MapTab, "system">, { nodes: MapNode[]; edges: Edge[] }> = {
  ingestion: {
    nodes: [
      node("upload", 0, 360, "Yükleme", "PDF, DOCX, Markdown ve metin kabul edilir.", "POST /workspaces/{id}/uploads", "Dosya boyutu ve biçimi doğrulanır."),
      node("upload-validation", 320, 360, "Dosya doğrulama", "Biçim, boyut ve workspace kapsamı denetlenir.", "Upload validation boundary", "Geçersiz içerik workflow başlatmaz."),
      node("duplicate-decision", 640, 360, "Sürüm kararı", "Aynı belge için yeni sürüm veya reddetme yolu seçilir.", "Document/version lookup", "Önceki sürümün kaynak kaydı korunur."),
      node("rejected", 960, 620, "Reddedilen yükleme", "Doğrulama, tekrar içerik veya ayrıştırma kuralını geçemeyen istek.", "API error envelope", "Belge, chunk veya workflow kaydı oluşturulmaz."),
    node("source-store", 960, 360, "Kaynak dosya kaydı · Disk", "Doğrulanan orijinal dosya workspace’in uploads alanına yazılır.", "Filesystem · workspace/uploads", "Kaynak dosya değişmeden korunur."),
      node("text-source-decision", 1280, 360, "Düz metin kaynağı mı?", ".md ve .txt dosyaları doğrudan okuma yoluna gider.", "Filename extension", "Markdown ve metin kaynakları Docling/OCR’a gönderilmez."),
      node("docling", 1600, 220, "Docling ayrıştırma", "PDF ve DOCX kaynakları Markdown’a çevrilir; DOCX Word Heading 2 stilleri ## olarak korunur.", "İç ayrıştırıcı sınırı", "Ayrıştırma hatası 422 ile sonlanır."),
      node("direct-text-read", 1600, 500, "Doğrudan UTF-8 okuma", "Markdown ve metin, içerik korunarak doğrudan okunur.", "UTF-8 text reader", "Geçersiz UTF-8 içerik 422 ile sonlanır."),
      node("normalized", 1920, 360, "Normalize Markdown · Disk", "Satır sonları normalize edilir ve çalışma kopyası workspace/normalized altında kaydedilir.", "Filesystem · workspace/normalized", "Dosya işlemi açık SQLite transaction dışında yapılır."),
      node("document-record", 2240, 360, "Belge sürümü · SQLite", "Belge, sürüm, dosya bilgileri ve sistem metadata’sı SQLite’a kaydedilir.", "SQLite · documents / versions / metadata", "Kullanıcı metadata’sı sistem değerlerini ezebilir."),
      node("logical-documents", 2560, 360, "Heading 2 → mantıksal belgeler", "Her ## başlığı ayrı metadata nesnesi ve mantıksal belge kaydı oluşturur; arşiv öneki eşleştirilmez.", "SQLite · logical_documents", "Metadata chunking başlamadan önce kaydedilir."),
      node("chunks", 2880, 360, "Chunk kayıtları · SQLite", "Her mantıksal belge token sınırı ve overlap ile bağımsız parçalanır.", "SQLite · chunks + next relationships", "Her chunk mantıksal belge kimliği, kodu, başlığı, sayfası ve kaynak adını taşır."),
      node("workflow", 3200, 360, "Ingestion run · SQLite", "Kalıcı ingestion run SQLite’a yazılır ve Dramatiq’e gönderilir.", "SQLite · workflow_runs; Redis", "Redis erişilemezse run queued olarak kalır."),
      node("ingestion-worker", 3520, 360, "Ingestion checkpointleri", "Parse, normalize, logical_documents, chunk ve index adımları kalıcı olarak izlenir.", "Document ingestion v3", "İptal ve yeniden deneme yalnızca güvenli adım sınırlarında uygulanır."),
    ],
    edges: links(["upload", "upload-validation"], ["upload-validation", "duplicate-decision"], ["upload-validation", "rejected", "geçersiz"], ["duplicate-decision", "source-store", "yeni içerik"], ["duplicate-decision", "rejected", "aynı içerik"], ["source-store", "text-source-decision"], ["text-source-decision", "docling", "PDF / DOCX"], ["text-source-decision", "direct-text-read", "MD / TXT"], ["docling", "normalized"], ["docling", "rejected", "ayrıştırılamadı"], ["direct-text-read", "normalized"], ["direct-text-read", "rejected", "geçersiz UTF-8"], ["normalized", "document-record"], ["document-record", "logical-documents", "yalnızca ##"], ["logical-documents", "chunks"], ["chunks", "workflow"], ["workflow", "ingestion-worker"]),
    [ingestionNodesKey]: detailedIngestionMap.nodes,
    [ingestionEdgesKey]: detailedIngestionMap.edges,
  },
  query: {
    nodes: [
      node("graph-job", 1600, 420, "GraphRAG query job", "API submits the durable query through Redis/Dramatiq; it does not execute Microsoft GraphRAG.", "QueryRun · Redis / Dramatiq", "Worker validates route and workspace scope."),
      node("graph-worker", 1920, 420, "GraphRAG Worker", "The worker executes Local, Global, or DRIFT with the user's selected provider/model.", "Worker-only Microsoft GraphRAG", "GraphRAG's answer is final; Cortex synthesis is skipped."),
      node("graph-result", 2240, 620, "GraphRAG final answer", "Usage, technical trace, and evidence metadata return to the API without a second LLM generation.", "QueryRun + GraphRAG reports", "Hybrid fallback is conditional on explicit policy."),
      node("chat", 0, 360, "Sohbet isteği", "Workspace ve konuşma kapsamındaki kullanıcı sorusu.", "POST /conversations/{id}/messages", "Konuşma sınırı korunur."),
      node("conversation-context", 320, 360, "Konuşma bağlamı", "Kayıt kaynağı: SQLite’taki workspace kapsamlı conversation ve message kayıtları.", "SQLite · conversations / messages", "Başka workspace’in geçmişi okunmaz."),
      node("router", 640, 360, "Sorgu planı", "Router, sorgu için retrieval yaklaşımını seçer.", "CustomQueryEngine adapters", "Yollar ayrı kalır; uygunsuz birleşim yapılmaz."),
      node("lookup-intent", 960, 360, "Yanıt biçimi niyeti", "Planlayıcı, belge listeleme dilini entity_document_lookup olarak işaretler ve needs_list değerini etkinleştirir.", "RouteSelection · intent / needs_list", "Belge listesi soruları özet yanıt yoluna düşmez."),
      node("hybrid", 960, 80, "Hibrit yol", "Dense, sparse, fusion ve reranking aşamalarını başlatır.", "Qdrant + bm25s", "Embedding uyumsuzsa dense arama engellenir."),
      node("dense", 1280, 20, "Dense retrieval", "Kayıt kaynağı: Qdrant Vector DB. Workspace filtresiyle benzerlik araması çalışır.", "Qdrant Vector DB · vector query", "Sadece aynı workspace adayları döner."),
      node("sparse", 1280, 230, "Sparse retrieval", "Kayıt kaynağı: workspace’e özel bm25s cache dosyaları. Terim araması aynı workspace indeksinde çalışır.", "Filesystem · bm25s workspace cache", "Dense arızasında kısmi sonuç sağlayabilir."),
      node("fusion", 1600, 125, "RRF fusion", "Dense ve sparse adayları reciprocal-rank fusion ile birleştirilir.", "Hybrid retrieval contract", "Aday kaynakları korunur."),
      node("reranker", 1920, 125, "Yerel BGE reranker", "Birleşen adaylar yerel modelle yeniden sıralanır.", "Local reranker adapter", "Model yoksa sonuçlar açık kısmi modda döner."),
      node("graph-ready", 960, 570, "Graph hazır mı?", "Kayıt kaynağı: SQLite’taki GraphRAG workspace state; güncellik ve sorgu kipi denetlenir.", "SQLite · graphrag_states", "Stale graph grounded cevap olarak sunulmaz."),
      node("graph-local", 1280, 470, "Graph Local", "Kayıt kaynağı: kanonik GraphRAG Parquet/JSON artefact’ları ve Qdrant vektör aynası.", "Filesystem · GraphRAG root; Qdrant vector mirror", "Kanonik graph verisi kullanılır."),
      node("graph-global", 1280, 670, "Graph Global", "Kayıt kaynağı: kanonik GraphRAG Parquet/JSON topluluk raporları ve Qdrant vektör aynası.", "Filesystem · GraphRAG root; Qdrant vector mirror", "Kanonik graph verisi kullanılır."),
      node("graph-drift", 1600, 570, "Graph DRIFT", "Kayıt kaynağı: GraphRAG Parquet/JSON ve Qdrant aynasındaki yerel/global kanıt.", "Filesystem · GraphRAG root; Qdrant vector mirror", "Modele sunulan kanıt ayrı normalize edilir."),
      node("document-group", 2240, 80, "Belgeye göre grupla", "Entity lookup adayları document_id ile gruplanır; aynı belgedeki eşleşen chunk’lar tek sonuç altında birleştirilir.", "DocumentMatch · document metadata + matched chunks", "Tam eşleşme ve belge çeşitliliği önceliklidir; her belge yalnızca bir kez döner."),
      node("evidence", 2240, 360, "Kanıt normalizasyonu", "Qdrant, bm25s cache veya GraphRAG artefact’larından gelen kaynaklar ortak Cortex evidence modeline dönüştürülür.", "Qdrant / filesystem cache / GraphRAG files", "Faktüel iddialar citation gerektirir."),
      node("citation-check", 2560, 360, "Citation kontrolü", "Kayıt kaynağı: SQLite belge, sürüm ve chunk kayıtlarıyla kaynak eşleşmesi doğrulanır.", "SQLite · documents / document_versions / chunks", "Desteksiz iddia grounded olarak işaretlenmez."),
      node("answer", 2880, 360, "Grounded yanıt", "Sentez, inference etiketi ve kaynak ayrıntıları.", "Provider answer adapter", "Desteksiz yanıtta citation yoktur."),
      node("answer-state", 3200, 360, "Yanıt durumu", "Yanıt, citation ve çalışma telemetry’si birlikte kaydedilir.", "Query run persistence", "Kullanıcı mesajları düzenlenebilir, yanıt geçmişi korunur."),
      node("history", 3520, 360, "Konuşma ve telemetry", "Mesajlar, query run, gecikme ve maliyet SQLite’a kaydedilir; geçmiş buradan okunur.", "SQLite · messages / query_runs / query_step_runs", "Geçmiş sayfa değişiminden bağımsızdır."),
    ],
    edges: links(["chat", "conversation-context"], ["conversation-context", "router"], ["router", "lookup-intent"], ["lookup-intent", "hybrid", "hybrid / lookup"], ["lookup-intent", "graph-ready", "graph"], ["hybrid", "dense"], ["hybrid", "sparse"], ["dense", "fusion"], ["sparse", "fusion"], ["fusion", "reranker"], ["reranker", "document-group", "needs_list"], ["reranker", "evidence", "passage QA"], ["document-group", "citation-check", "benzersiz belgeler"], ["graph-ready", "graph-local", "local"], ["graph-ready", "graph-global", "global"], ["graph-local", "graph-drift"], ["graph-global", "graph-drift"], ["graph-drift", "evidence"], ["graph-ready", "hybrid", "hazır değil"], ["evidence", "citation-check"], ["citation-check", "answer", "kanıtlı"], ["citation-check", "answer-state", "eksik citation"], ["answer", "answer-state"], ["answer-state", "history"]),
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

// The query map keeps Hybrid and GraphRAG answer paths distinct. GraphRAG transport is a
// worker boundary, so remove the legacy direct graph edges before adding the durable job path.
staticMaps.query.edges = staticMaps.query.edges.filter(
  (edge) => !["graph-ready-graph-local", "graph-ready-graph-global", "graph-local-graph-drift", "graph-global-graph-drift", "graph-drift-evidence", "graph-ready-hybrid"].includes(edge.id),
);
staticMaps.query.edges.push(
  ...links(
    ["graph-ready", "graph-job", "submit"],
    ["graph-job", "graph-worker", "Redis / Dramatiq"],
    ["graph-worker", "graph-local", "Local"],
    ["graph-worker", "graph-global", "Global map/reduce"],
    ["graph-worker", "graph-drift", "DRIFT limits"],
    ["graph-local", "graph-result"],
    ["graph-global", "graph-result"],
    ["graph-drift", "graph-result"],
    ["graph-result", "answer-state", "format only"],
    ["graph-ready", "hybrid", "explicit fallback policy"],
  ),
);

function node(id: string, x: number, y: number, label: string, description: string, interfaces: string, guarantee: string): MapNode {
  return { id, type: "architecture", position: { x, y }, data: { label, description, interfaces, guarantee, ...nodePresentation(id) }, style: { width: 205, zIndex: 1 } };
}
function links(...pairs: [string, string, string?][]): Edge[] { return pairs.map(([source, target, label]) => ({ id: `${source}-${target}`, source, target, label, animated: true, style: { stroke: "var(--cortex-secondary)", strokeWidth: 1.5 }, labelStyle: { fill: "var(--cortex-muted)", fontSize: 11, fontWeight: 650 }, labelBgStyle: { fill: "var(--cortex-surface)", fillOpacity: 0.92 } })); }
function nodePresentation(id: string): Pick<MapNodeData, "kind" | "layer" | "model"> {
  if (id === "community-detection") return { kind: "processor", layer: "Algorithmic graph analysis" };
  if (id === "claims-optional") return { kind: "decision", layer: "Optional GraphRAG stage" };
  if (id === "community-reports") return { kind: "llm-api", layer: "User-selected GraphRAG model", model: "Community report model" };
  if (id === "graph-job") return { kind: "service", layer: "Durable request" };
  if (id === "graph-worker") return { kind: "worker", layer: "Worker-only execution" };
  if (id === "graph-result") return { kind: "storage", layer: "Durable final result" };
  const values: Record<string, Pick<MapNodeData, "kind" | "layer" | "model">> = {
    ...detailedNodePresentation,
    upload: { kind: "input", layer: "Kullanıcı girişi" }, "upload-validation": { kind: "safety", layer: "Yükleme güvenliği" }, "duplicate-decision": { kind: "decision", layer: "Sürümleme" }, rejected: { kind: "safety", layer: "Reddedilen istek" }, "source-store": { kind: "storage", layer: "Kaynak depolama" }, "text-source-decision": { kind: "decision", layer: "Belge işleme" }, "direct-text-read": { kind: "processor", layer: "Belge işleme" }, docling: { kind: "processor", layer: "Belge işleme" }, normalized: { kind: "storage", layer: "Normalize kaynak kaydı" }, "document-record": { kind: "storage", layer: "Kalıcı belge kaydı" }, chunks: { kind: "storage", layer: "Kalıcı chunk kaydı" }, workflow: { kind: "storage", layer: "Kalıcı workflow kaydı" }, "ingestion-worker": { kind: "worker", layer: "Arka plan" }, metadata: { kind: "llm-api", layer: "Metadata", model: "Metadata modeli · API" }, embedding: { kind: "llm-local", layer: "Embedding", model: "Embedding modeli · Local" }, qdrant: { kind: "storage", layer: "Dense retrieval" }, "sparse-index": { kind: "storage", layer: "Sparse retrieval" }, "graph-decision": { kind: "decision", layer: "GraphRAG koşulu" }, graphrag: { kind: "llm-api", layer: "Graph indeksleme", model: "GraphRAG provider · API" }, sqlite: { kind: "storage", layer: "Kalıcı durum" },
    chat: { kind: "input", layer: "İstek" }, "conversation-context": { kind: "processor", layer: "Konuşma kapsamı" }, router: { kind: "decision", layer: "Sorgu planı" }, "lookup-intent": { kind: "decision", layer: "Yanıt biçimi" }, hybrid: { kind: "retrieval", layer: "Hibrit retrieval" }, dense: { kind: "retrieval", layer: "Dense retrieval" }, sparse: { kind: "retrieval", layer: "Sparse retrieval" }, fusion: { kind: "processor", layer: "Aday birleştirme" }, reranker: { kind: "llm-local", layer: "Reranking", model: "BGE reranker · Local" }, "document-group": { kind: "processor", layer: "Belge sonuçları" }, "graph-ready": { kind: "decision", layer: "GraphRAG koşulu" }, "graph-local": { kind: "retrieval", layer: "GraphRAG Local" }, "graph-global": { kind: "retrieval", layer: "GraphRAG Global" }, "graph-drift": { kind: "retrieval", layer: "GraphRAG DRIFT" }, evidence: { kind: "safety", layer: "Kanıt güvenliği" }, "citation-check": { kind: "decision", layer: "Citation kontrolü" }, answer: { kind: "llm-api", layer: "Yanıt sentezi", model: "Yanıt modeli · API" }, "answer-state": { kind: "storage", layer: "Query telemetry" }, history: { kind: "storage", layer: "Kalıcı durum" },
    ui: { kind: "input", layer: "Kullanıcı arayüzü" }, api: { kind: "service", layer: "Komut sınırı" }, definition: { kind: "service", layer: "Workflow tanımı" }, state: { kind: "storage", layer: "Kalıcı durum" }, "lock-decision": { kind: "decision", layer: "Eşzamanlılık" }, redis: { kind: "service", layer: "Broker" }, worker: { kind: "worker", layer: "Arka plan" }, checkpoint: { kind: "storage", layer: "Dayanıklılık" }, "retry-decision": { kind: "decision", layer: "Recovery" }, cancel: { kind: "safety", layer: "İptal ve recovery" }, sse: { kind: "delivery", layer: "Canlı teslim" },
  };
  return { ...values, ...importantIndexingPresentation }[id] ?? { kind: "service", layer: "Platform" };
}

function ArchitectureNode({ data, selected }: NodeProps<MapNode>) {
  return <article className={`architecture-node is-${data.kind}${selected ? " is-selected" : ""}`}>
    <Handle type="target" position={Position.Left} />
    <span className="architecture-node__layer">{data.layer}</span>
    <strong>{data.label}</strong>
    {data.kind === "decision" && <span className="architecture-node__decision">Karar noktası</span>}
    {data.model && <span className={`architecture-node__model-type is-${data.kind}`}>{data.kind === "llm-local" ? "LLM · Local" : data.kind === "llm-api" ? "LLM · API" : "Model · Local"}</span>}
    <small>{data.description}</small>
    <Handle type="source" position={Position.Right} />
  </article>;
}

function FlowGroup({ data }: NodeProps<FlowGroupNode>) {
  return <section className="flow-group"><span>{data.label}</span></section>;
}

const nodeTypes: NodeTypes = { architecture: ArchitectureNode, "flow-group": FlowGroup };

function flowGroups(tab: MapTab): FlowGroupNode[] {
  const groups: Record<MapTab, Array<[string, number, number, number, number]>> = {
    system: [["Cortex platform services", -60, -60, 1080, 780]],
    ingestion: [["Giriş ve doğrulama", -80, -40, 1180, 900], ["Belge işleme ve kalıcı kayıt", 1120, -40, 3200, 900], ["Dayanıklı ingestion", 4340, -40, 1360, 900], ["İndeksleme", 5820, -40, 1160, 900]],
    query: [["İstek ve planlama", -80, -40, 920, 900], ["Retrieval ve GraphRAG", 880, -40, 1240, 900], ["Kanıt ve yanıt", 2160, 230, 1700, 420]],
    workflows: [["Komut ve tanım", -80, -40, 920, 900], ["Durable orchestration", 880, -40, 1580, 900], ["İlerleme teslimi", 2480, -40, 380, 900]],
  };
  return groups[tab].map(([label, x, y, width, height], index) => ({
    id: `flow-group-${tab}-${index}`,
    type: "flow-group",
    position: { x, y },
    data: { label },
    draggable: false,
    selectable: false,
    focusable: false,
    style: { height, pointerEvents: "none", width, zIndex: 0 },
  }));
}

export function ASystemMap() {
  const [services, setServices] = useState<Record<string, string>>({ backend: "unknown" });
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [activeTab, setActiveTab] = useState<MapTab>("system");
  const [selectedId, setSelectedId] = useState("backend");
  const [detailTab, setDetailTab] = useState<DetailTab>("description");
  const [detailsOpen, setDetailsOpen] = useState(false);
  useEffect(() => {
    const refresh = () => Promise.all([apiClient.getHealth(), apiClient.diagnostics()]).then(([health, diagnostics]) => setServices({ ...health.services, recovery: diagnostics.workflows.interrupted ? "attention" : "healthy", reconciliation: diagnostics.reconciliation.state })).catch(() => setServices({ backend: "unavailable" }));
    void refresh(); const timer = window.setInterval(() => void refresh(), 15_000); return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { void apiClient.getSettings().then(({ settings: values }) => setSettings(values)).catch(() => undefined); }, []);
  const systemMap = useMemo(() => ({
    nodes: [["frontend", "healthy"], ...Object.entries(services).filter(([id]) => id !== "frontend")].map(([id, status], index): MapNode => ({
      ...node(id, (index % 3) * 320, Math.floor(index / 3) * 190, `${id.replaceAll("_", " ")} · ${status}`, serviceDescription(id), serviceInterface(id), serviceGuarantee(id)),
      style: { width: 190, zIndex: 1 },
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
  const mapNodes = useMemo(() => [...flowGroups(activeTab), ...map.nodes], [activeTab, map.nodes]);
  const selectTab = (tab: MapTab) => { setActiveTab(tab); setSelectedId((tab === "system" ? systemMap : staticMaps[tab]).nodes[0]?.id ?? ""); setDetailTab("description"); setDetailsOpen(false); };
  const visibleEdges = map.edges.filter((edge) => map.nodes.some((item) => item.id === edge.source) && map.nodes.some((item) => item.id === edge.target));
  return <section className="system-map page-stack">
    <ATabs className="system-map__tabs" aria-label="Sistem haritası görünümleri">{(Object.keys(tabLabels) as MapTab[]).map((tab) => <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? "is-active" : undefined} onClick={() => selectTab(tab)}>{tabLabels[tab]}</button>)}</ATabs>
    <div className="system-map__legend" aria-label="Düğüm renkleri lejantı">{legendGroups.map((group) => <section key={group.label} className="system-map__legend-group"><strong>{group.label}</strong><div>{group.items.map((item) => <span key={item.kind} className={`system-map__legend-item is-${item.kind}`}><i aria-hidden="true" />{item.label}</span>)}</div></section>)}</div>
    <div className={`system-map__layout${detailsOpen ? " is-detail-open" : ""}`}><ACard title={tabLabels[activeTab]}><AFlowCanvas nodes={mapNodes} edges={visibleEdges} nodeTypes={nodeTypes} onNodeClick={(id) => { setSelectedId(id); setDetailTab("description"); setDetailsOpen(true); }} height={620} showMiniMap /></ACard><aside className="system-map__sidebar" aria-hidden={!detailsOpen}><div className="system-map__sidebar-header"><div><span>Seçili bileşen</span><h2 className="text-lg">{selected?.data.label}</h2></div><button type="button" className="system-map__sidebar-close" aria-label="Seçili bileşen ayrıntılarını kapat" onClick={() => setDetailsOpen(false)}>×</button></div><ATabs className="system-map__detail-tabs" aria-label="Bileşen ayrıntıları">{(["description", "interfaces", "guarantee"] as DetailTab[]).map((tab) => <button key={tab} type="button" role="tab" aria-selected={detailTab === tab} className={detailTab === tab ? "is-active" : undefined} onClick={() => setDetailTab(tab)}>{({ description: "Açıklama", interfaces: "Arayüz", guarantee: "Garanti" } as Record<DetailTab, string>)[tab]}</button>)}</ATabs>{detailTab === "description" && selected?.data.model && <div className="system-map__model-detail"><strong>{selected.data.kind === "llm-local" ? "LLM · Local" : selected.data.kind === "llm-api" ? "LLM · API" : "Yerel model"}</strong><span>{selected.data.model}</span><p>{modelDescription(selected.data.kind, selected.data.model)}</p></div>}<p>{detailTab === "description" ? selected?.data.description : detailTab === "interfaces" ? selected?.data.interfaces : selected?.data.guarantee}</p></aside></div>
    <AInfoPanel title="Okuma biçimi">Yeşil düğümler canlı sağlık kontrolünden gelir. Belge akışı yükleme sırasında uygulanan sıralı yolu gösterir: Markdown ve metin doğrudan okunur; PDF ve DOCX Docling üzerinden ayrıştırılır. DOCX Heading 2 stilleri Markdown ## sınırlarına dönüşür ve her sınır chunking öncesinde ayrı bir mantıksal belge olur. Kalıcı kayıt düğümleri kaynak dosyayı, normalize Markdown’ı, belge sürümünü, mantıksal belgeleri, chunk’ları, workflow run’ını ve checkpoint’leri gösterir. Dense reindex ve GraphRAG reindex, bu hattın dalları değil; ayrı tetiklenen dayanıklı işlerdir.</AInfoPanel>
  </section>;
}

function serviceDescription(id: string) { return ({ frontend: "React/Vite kullanıcı arayüzü.", backend: "FastAPI komut ve sorgu sınırı.", worker: "Dramatiq tabanlı kalıcı iş yürütücüsü.", sqlite: "İlişkisel kayıt teknolojisi: workspace, belge, durum ve telemetry için SQLite.", redis: "Dramatiq broker ve iş teslimi.", qdrant: "Vektör kayıt teknolojisi: workspace filtreli dense retrieval için Qdrant Vector DB.", ollama: "Yerel embedding ve model sağlayıcısı.", graphrag: "Worker-owned GraphRAG bağımlılığı; kanonik çıktılar Parquet/JSON dosyalarıdır.", openai: "İsteğe bağlı OpenAI sağlayıcı bağlantısı.", anthropic: "İsteğe bağlı Anthropic sağlayıcı bağlantısı.", recovery: "Kesilmiş workflow kurtarma durumu.", reconciliation: "Orphan kaynak uzlaştırma durumu." } as Record<string, string>)[id] ?? "Cortex servis bileşeni."; }
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
function modelDescription(kind: NodeKind, model: string) {
  if (kind === "llm-local") return `${model} bu makinede Ollama veya yerel model adaptörü üzerinden çalışır; içerik harici bir sağlayıcıya gönderilmez.`;
  if (kind === "llm-api") return `${model} yapılandırılmış sağlayıcının API’si üzerinden çağrılır; sağlayıcı ve model ayarları Ayarlar ekranından gelir.`;
  return `${model} retrieval adaylarını yerel olarak yeniden sıralamak için kullanılır.`;
}
