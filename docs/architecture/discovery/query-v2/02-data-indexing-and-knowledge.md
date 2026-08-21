# Query Architecture V2: veri, indeksleme ve graph mevcut durumu

> Bu paket mevcut durum araştırmasıdır; açıklayıcıdır, bağlayıcı hedef mimari değildir. İnceleme tarihi: 2026-08-16.

## Authoritative veri ve workspace sınırı

SQLite'daki temel zincir `Workspace → Document → DocumentVersion → LogicalDocument → Chunk`tır. `documents` kaynak belge kaydını, `document_versions` kaynak/normalize dosya yollarını ve hashlerini, `logical_documents` Heading 2 ile ayrılmış ilk sınıf belge parçalarını, `chunks` ise retrieval kanıtını taşır. `chunk_relationships` yalnızca aynı sürüm içindeki `next` komşuluğudur; knowledge-graph relation değildir. Bütün ilgili relational modeller `workspace_id` taşır.

`document_metadata` key/value JSON ve origin (`system`, `extracted`, `user`) precedence saklar; typed entity/date/fact schema değildir. `conversations`, `messages`, `query_runs`, `query_step_runs` sorgu geçmişi/trace; `workflow_*`, locks ve `usage_events` operational durable state'tir. `workspace_resources`, `workspace_index_states`, `graphrag_states` kaynak path/readiness/hash durumunu taşır.

Yok olan tablolar: canonical entities, aliases, entity mentions, entity relations, events, claims, verified facts, properties/property claims, citations/provenance. Citation/provenance mevcutta message JSON, BM25/Qdrant `Evidence` ve transient property claim alanlarına dağılmıştır.

## Ingestion ve retrieval projeksiyonları

`api/uploads.py` güvenli upload ve versiyonlamadan sonra Docling (PDF/DOCX) veya doğrudan MD/TXT parser kullanır, normalized Markdown yazar. `ingestion/logical_documents.py` yalnızca `##` sınırında logical document üretir. `chunking.py` deterministic heading-aware word chunks üretir; chunklar logical document sınırını geçmez. Workflow tanımı `parse → normalize → logical_documents → chunk → index` checkpointleri taşır.

`retrieval/indexing.py:rebuild_active_workspace()` aktif ve silinmemiş chunklardan iki projection üretir:

* Workspace klasöründe BM25 corpus ve serialised `Evidence` (`WorkspaceBM25Index`).
* Paylaşımlı collection içinde, zorunlu `workspace_id` payload filtresiyle Qdrant dense chunk points (`WorkspaceQdrantStore`).

Qdrant chunk payloadı content, chunk/document/version ID, citation label, embedding configuration hash ve `chunk.metadata_json` içindeki alanları taşır. Kodun tanımladığı semantic entity/date/property filter sözleşmesi yoktur; payload indexleri workspace, document, document version, folder ve embedding hash içindir. Active embedding fingerprint uyumsuz dense okumayı/yazmayı engeller; full rebuild eski workspace projection'ını silip yenisini üretir. BM25 ve Qdrant rebuildable query projectiontır, source authority değildir.

Top-k hybrid retrieval exhaustive enumeration olamaz; rulebook verified count'un top-k'dan çıkarılmasını açıkça yasaklar. Yeni first-class entity/relation/event/temporal/fact katmanı parser, normalized Markdown, logical-document/chunk provenance, workspace context, workflow ve reindex altyapısını yeniden kullanabilir; fakat yeni persistence/extraction ve mevcut corpus için backfill gerektirir.

## Property aggregation

`aggregation/property.py` bilinçli olarak property-domain'e özeldir. `extract_property_claims()` candidate chunk'ta label-bound pafta/ada/parsel/bağımsız bölüm, yer alanları, local ownership span, share ve kaynak document/version/chunk/citation bilgisi çıkarır. Missing cadastral values doldurulmaz; date/legal number/contextless fraction share sayılmaz. Claim query-time geçicidir ve kalıcı tabloya yazılmaz.

`PropertyClaim.identity_key`, bilinen province/district/neighborhood/sheet/block/parcel/section alanlarının normalize alt kümesidir. Aynı key'deki claimler `PropertyRecord` altında deduplicate olur, çatışan share'ler görünür. `AggregationResult` candidate/processed belge-chunk sayıları, claim sayıları, dedup count ve complete bayrağını verir. Yeniden kullanılabilecek kavramlar: candidate accounting, typed claim, provenance, normalized identity, conflict/dedup ve completeness telemetry. Property vocabulary, Turkish ownership regexleri, cadastral identity/share ve display genel aggregation katmanı değildir.

## Tarih/temporal durum

Operational timestamps (`created_at`, `updated_at`, `deleted_at`) dışında relational semantic date field yoktur. Metadata ve chunk metadata serbest JSON'dur. Planner yalnızca yıl/yıl-aralığı tanır; date constraint index/SQL filtresi olarak uygulanmaz. Property extraction ilk date-like değeri `record_date` yapabilir ama persist/query edilmez. GraphRAG temporal relation modeli Cortex tarafından okunmaz. Bu nedenle tam tarih, multiple/partial date, event date ile document date ayrımı ve entity/event temporal bağları mevcut değildir.

## Graph sistemleri

Microsoft GraphRAG `graphrag==2.6.0` ile workspace root altında input/settings/native Parquet/JSON artifacts üretir. `GraphRAGInputMaterializer` active logical document başına Markdown üretir. `GraphRAGAdapter` entity, relationship, report, text unit artifactlarını okur; Local/Global/DRIFT CLI query yöntemlerini ayrı çağırır. Claim extraction optional/default-off'tur. Model/provider global settings'ten gelir; GraphRAG worker-owned'dur.

GraphRAG entity/report/text-unit vektörleri Qdrant'a ayrı collection'lara mirror edilir; upstream GraphRAG output bu engine için canonical, mirror projectiondır. `rebuild_networkx()` artifactlardan `nx.MultiDiGraph` üretip workspace `networkx.graphml` dosyasına yazar. NetworkX chat engine değildir; Graph explorer API artifactları okur. Bağımsız Cortex knowledge graph, graph database veya graph traversal query interface yoktur. Neo4j, Memgraph, Kuzu, FalkorDB ve ArangoDB entegrasyonu bulunmamıştır.

## Runtime/storage tablosu

| Store | Rol | Durum |
|---|---|---|
| SQLite | source metadata, chat/workflow/index state | durable authority; fact/graph store değil |
| workspace filesystem | upload, normalized Markdown, BM25, GraphRAG, GraphML | source/artifact root; indexler rebuildable |
| Qdrant | dense chunks, GraphRAG vector mirror | workspace-filtered rebuildable projection |
| BM25 files | sparse corpus/evidence | workspace-local rebuildable projection |
| Redis/Dramatiq | durable run'ların teslim/worker sınırı | broker; authority SQLite |
| Ollama/OpenAI/Anthropic | provider | dış servis, veri authority değil |

