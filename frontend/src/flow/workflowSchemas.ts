export type WorkflowStepSchema = {
  id: string;
  label: string;
  description: string;
  technology: string;
  guarantee: string;
  substeps?: WorkflowStepSchema[];
};

export type WorkflowSchema = {
  label: string;
  version: string;
  steps: WorkflowStepSchema[];
};

/**
 * The durable workflow view and the System map deliberately use this one
 * description. Runtime state is overlaid by ProcessesPage; it never changes
 * the versioned workflow definition shown here.
 */
export const workflowSchemas: Record<string, WorkflowSchema> = {
  ingestion: {
    label: "Belge ingestion",
    version: "v3 · document-ingestion",
    steps: [
      { id: "parse", label: "Ayrıştır", description: "MD/TXT UTF-8 olarak okunur; PDF ve DOCX Docling üzerinden Markdown'a dönüştürülür.", technology: "Docling / UTF-8", guarantee: "Geçersiz veya ayrıştırılamayan kaynak güvenli biçimde reddedilir." },
      { id: "normalize", label: "Normalize et", description: "Başlıklar ve metin korunarak normalize Markdown kalıcı kaynak olarak hazırlanır.", technology: "Workspace filesystem", guarantee: "Kaynak dosya ve normalize içerik ayrı saklanır." },
      { id: "logical_documents", label: "Mantıksal belgeler", description: "Her Markdown ## sınırı ayrı mantıksal belge kaydı oluşturur; chunk ve GraphRAG girdileri bu kimliği devralır.", technology: "SQLite · logical_documents", guarantee: "Arşiv öneki eşleştirilmez; yalnızca Heading 2 sınırdır." },
      { id: "chunk", label: "Chunk'la", description: "Mantıksal belge bağlamını koruyan retrieval parçaları ve ilişkileri üretilir.", technology: "SQLite · chunks", guarantee: "Her chunk workspace ve belge sürümüne bağlıdır." },
      { id: "index", label: "İndeksle", description: "Dense, sparse ve GraphRAG yaşam döngülerinin hazır/reindex gerekli durumu güncellenir.", technology: "SQLite · index state", guarantee: "GraphRAG ve dense reindex ayrı, dayanıklı işler olarak tetiklenir." },
    ],
  },
  dense_reindex: {
    label: "Dense embedding reindex",
    version: "v2 · dense-reindex",
    steps: [
      { id: "clear_active_vectors", label: "Aktif vektörleri hazırla", description: "Güvenli yeniden indeksleme için aktif dense vektör alanı temizleme/migrasyon sınırına alınır.", technology: "Qdrant", guarantee: "Workspace payload filtresi olmadan silme yapılmaz." },
      { id: "embed", label: "Embedding üret", description: "Yapılandırılmış embedding sağlayıcısı ile uyumlu hazırlama politikası kullanılarak vektörler oluşturulur.", technology: "Embedding adapter", guarantee: "Boyut ve yapılandırma uyumsuzluğu upsert öncesi engellenir." },
      { id: "upsert", label: "Vektörleri yaz", description: "Vektörler batch halinde workspace kapsamıyla Qdrant'a yazılır.", technology: "Qdrant", guarantee: "Her kayıt workspace_id payload'ı taşır." },
      { id: "activate", label: "Aktifleştir", description: "Yeni dense indeks aktif durum olarak işaretlenir ve sorgu yeniden açılır.", technology: "SQLite · index state", guarantee: "Tutarsız indeks etkinleştirilmez." },
    ],
  },
  graphrag_reindex: {
    label: "GraphRAG reindex",
    version: "v1 · graphrag-reindex",
    steps: [
      { id: "snapshot", label: "Snapshot al", description: "Workspace kapsamındaki uygun kaynakların GraphRAG girdisi için tutarlı görüntüsü alınır.", technology: "Workspace graph root", guarantee: "Graph işlemleri workspace graph lock ile seri yürür." },
      { id: "materialize", label: "Girdileri hazırla", description: "GraphRAG text unit ve çalışma girdileri canonical graph çalışma alanına yazılır.", technology: "Parquet / JSON", guarantee: "Cortex chunk'ları GraphRAG text unit'lerinden ayrı kalır." },
      {
        id: "index",
        label: "Grafı indeksle",
        description: "Microsoft GraphRAG kanonik pipeline'ı varlık, ilişki ve topluluk artefact'larını üretir.",
        technology: "Microsoft GraphRAG",
        guarantee: "Kanonik graph verisi her workspace'in kendi kökünde kalır.",
        substeps: [
          { id: "entity_extraction", label: "Varlık ve ilişki çıkarımı", description: "Metinden varlıklar ve aralarındaki ilişkiler seçili extraction modeliyle çıkarılır.", technology: "GraphRAG extraction LLM", guarantee: "Workspace graph kökü dışında veri işlenmez." },
          { id: "description_summarization", label: "Açıklamaları özetle", description: "Varlık ve ilişki açıklamaları aranabilir kanonik içerik için özetlenir.", technology: "GraphRAG summary LLM", guarantee: "Kaynak GraphRAG artefact'ları korunur." },
          { id: "community_report_generation", label: "Topluluk raporları", description: "Graph toplulukları için özet raporlar üretilir.", technology: "GraphRAG community LLM", guarantee: "Global GraphRAG sorgu yolu için ayrı rapor artefact'ları üretilir." },
          { id: "embedding", label: "Embedding", description: "GraphRAG girdileri seçili embedding sağlayıcısı ve modeliyle vektörlenir.", technology: "Embedding provider", guarantee: "Model ve tokenizer ayarları çalışma başında sabitlenir." },
        ],
      },
      { id: "mirror", label: "Vektör aynasını güncelle", description: "GraphRAG kaynak türleri ayrıştırılmış Qdrant vektör aynasına yazılır.", technology: "Qdrant + GraphRAG artifacts", guarantee: "Entity, report ve text-unit vektörleri birbirine karıştırılmaz." },
    ],
  },
  knowledge_reindex: {
    label: "Knowledge construction reindex",
    version: "v1 · knowledge-reindex",
    steps: [
      { id: "source_relational", label: "Source snapshot", description: "Captures the active workspace corpus and source fingerprint.", technology: "SQLite", guarantee: "Only one workspace-scoped candidate generation is used." },
      { id: "entity_mention", label: "Entity and mention extraction", description: "Extracts exact-span proposals through the configured provider.", technology: "Knowledge extractor", guarantee: "Hallucinated or cross-workspace spans are rejected." },
      { id: "identity_resolution", label: "Identity resolution", description: "Applies conservative evidence-based identity decisions.", technology: "Knowledge identity", guarantee: "Ambiguous matches remain unresolved." },
      { id: "relation", label: "Relation extraction", description: "Builds exact-evidence relation proposals.", technology: "Knowledge relations", guarantee: "Chunk co-occurrence is not relation evidence." },
      { id: "event", label: "Event extraction", description: "Builds evidence-bound events and participants.", technology: "Knowledge events", guarantee: "Participants stay workspace-scoped." },
      { id: "temporal", label: "Temporal processing", description: "Preserves original temporal text and uncertainty.", technology: "Knowledge temporal", guarantee: "Approximate values remain uncertain." },
      { id: "claim_fact", label: "Claim and fact validation", description: "Produces supported claims and validated facts.", technology: "Knowledge claims", guarantee: "Confidence alone never verifies a fact." },
      { id: "canonical_graph", label: "Canonical graph promotion", description: "Promotes exact-evidence proposals without overwriting curation.", technology: "Neo4j", guarantee: "Authority precedence is enforced." },
      { id: "bm25", label: "BM25 projection", description: "Builds the workspace sparse projection.", technology: "bm25s", guarantee: "Output is bound to the candidate fingerprint." },
      { id: "dense_qdrant", label: "Dense/Qdrant projection", description: "Builds workspace-filtered dense vectors.", technology: "Qdrant", guarantee: "Output is bound to the candidate fingerprint." },
      { id: "graphrag", label: "GraphRAG projection", description: "Builds and verifies the GraphRAG projection.", technology: "Microsoft GraphRAG", guarantee: "A different GraphRAG generation cannot activate this candidate." },
    ],
  },
  document_delete: {
    label: "Belge silme", version: "v1 · document-delete", steps: [
      { id: "mark", label: "Silme için işaretle", description: "Belge silme isteği durable run olarak kaydedilir.", technology: "SQLite", guarantee: "Silme akışı idempotenttir." },
      { id: "cleanup", label: "Kaynakları temizle", description: "İlişkisel ve harici kaynaklar güvenli temizleme sınırında uzlaştırılır.", technology: "SQLite + storage adapters", guarantee: "Kısmi hata onarım işi oluşturur." },
      { id: "reconcile", label: "Uzlaştır", description: "Kalan kaynaklar için onarım durumu oluşturulur.", technology: "Reconciliation workflow", guarantee: "Store'lar arasında sessiz orphan bırakılmaz." },
    ],
  },
  workspace_delete: {
    label: "Workspace silme", version: "v1 · workspace-delete", steps: [
      { id: "mark", label: "Silme için işaretle", description: "Workspace silme isteği kalıcı olarak kaydedilir.", technology: "SQLite", guarantee: "İş tekrarlandığında güvenli kalır." },
      { id: "cleanup", label: "Kaynakları temizle", description: "Workspace'e ait veri depolarının temizliği yürütülür.", technology: "SQLite + storage adapters", guarantee: "Kısmi hata onarım işi oluşturur." },
      { id: "reconcile", label: "Uzlaştır", description: "Silme sonrası orphan denetimi yapılır.", technology: "Reconciliation workflow", guarantee: "Çapraz-store kalıntılar görünür kalır." },
    ],
  },
  reconcile: {
    label: "Orphan uzlaştırma", version: "v1 · orphan-reconciliation", steps: [
      { id: "scan", label: "Tara", description: "Veri depoları arasındaki ilişki ve kaynak tutarlılığı denetlenir.", technology: "SQLite + storage adapters", guarantee: "Kapsam ve istek sahibi workflow olayında saklanır." },
      { id: "repair", label: "Onar", description: "Bulunan güvenli onarımlar kalıcı checkpoint ile uygulanır.", technology: "Durable workflow", guarantee: "Onarım tekrar çalıştırılabilir." },
    ],
  },
};

export function workflowSchema(jobType: string) {
  return workflowSchemas[jobType];
}
