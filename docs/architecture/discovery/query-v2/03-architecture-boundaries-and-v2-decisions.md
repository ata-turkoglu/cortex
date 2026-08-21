# Query Architecture V2: mimari sınırlar, testler ve karar noktaları

> Bu paket mevcut durum araştırmasıdır; açıklayıcıdır, bağlayıcı hedef mimari değildir. İnceleme tarihi: 2026-08-16.

## Mevcut repository sınırları

`backend/app/chat/` query understanding, entity resolution, route selection, engine orchestration, evidence rendering ve synthesis'i birlikte barındırır. `retrieval/` Qdrant/BM25/embedding/rerank; `aggregation/` yalnızca property; `graphrag/` upstream adapter/materialization/mirroring/NetworkX; `ingestion/` parser/logical boundary/chunking; `workflows/` durable execution sorumluluğundadır. Modeller `models.py` altında merkezidir. `/system-map` tamamen `frontend/src/flow/ASystemMap.tsx` içinde manually declared React Flow nodes/edges ile tanımlıdır.

Bu, gelecekte `query`, `knowledge`, `query_engines` sınırlarına evrilebilir; ancak doğrudan yeni klasör açmak `chat`, `retrieval`, `graphrag` ile duplication yaratır. En belirgin sorumluluk birleşmesi `chat/service.py` içindedir.

AI navigation vendor-neutraldır: root/scoped `AGENTS.md`, `.ai/project-map.yaml`, `docs/ai/index.md`, `CLAUDE.md`/`GEMINI.md` adapterları ve context validation scriptleri vardır. Entity/fact/structured query için provider-neutral canonical subsystem dokümanı yoktur.

## System map ve kod gerilimi

`ASystemMap` tabları `system`, `ingestion`, `query`, `workflows`tir. Query görünümü aşağıdaki konseptleri zaten gösterir:

```
chat/context → QueryPlan + entity resolution → route
  ├─ hybrid: dense + BM25 → RRF → BGE → evidence selection
  ├─ document grouping
  ├─ property claims → entity binding → dedup/completeness
  └─ GraphRAG Local/Global/DRIFT → evidence
       → citation finalization → answer → telemetry
```

Query understanding, retrieval, GraphRAG, property aggregation, evidence/citation, answer ve indexing kavramsal olarak mevcuttur. Typed IR validator, execution planner/optimizer, generic structured engine, canonical KG, relation/event/temporal engine ve provenance graph yeni kavramlardır. Diagram değiştirilmedi.

Kodla üç önemli fark vardır: (1) `MASTER_PROMPT.md` multi-route LlamaIndex beklentisi belirtir, fakat production GraphRAG seçildiğinde hybrid ile sonuç birleştirmez. (2) Diagram Local→DRIFT akışını gösterir; natural-language router Local/DRIFT seçmez, broad/deep için Global seçer. (3) Diagramdaki “verified aggregation” gerçek entity/property truth completeness değil, active-corpus scan tamamlanma anlamındadır.

## Test ve evaluation durumu

Güçlü davranış testleri: `test_query_plan.py` (operation/aggregation safety/year/entity workspace scope), `test_property_aggregation.py` (cadastral labels, share ownership, dedup/provenance), `test_evidence_selection.py`, `test_entity_document_lookup.py`, `test_retrieval.py`, retrieval benchmarks/embeddings, `test_citations.py`, GraphRAG adapter/qdrant/worker testleri, multi-document ingestion, workspace/API/context testleri ve `ASystemMap.test.tsx`.

Canonical alias/mention, surname enumeration, generic COUNT/LIST/GROUP/RANK, relation traversal, exact date/temporal filter, graph-plus-retrieval composition ve persisted fact model için test yoktur; ilgili capability de yoktur. `app/evaluation/runner.py` versioned synthetic golden suite üzerinden production chat orchestration çalıştırır; eligible labelled cases için MRR, hit@k, recall@k, rank ve compatible baseline regression üretir. Archive truth veya exhaustive semantics testi değildir.

## V2 kavramlarının mevcut statüsü

| Kavram | Statü | Mevcut karşılık |
|---|---|---|
| Semantic query understanding | kısmi | deterministic regex `plan_query()` |
| Typed/logical Query IR / validator | kısmi | frozen `QueryPlan`, dataclass typing |
| Execution planner / optimizer | yok | split QueryPlan + RouteSelection |
| Structured / generic aggregation | kısmi / yok | property-only aggregation |
| Canonical entity, mention, relation store | yok | chunk/metadata/GraphRAG artifacts |
| Event, temporal relation, verified fact | yok | serbest text/metadata, transient property date |
| Cortex knowledge graph / graph database | yok | upstream GraphRAG + derived NetworkX |
| Hybrid multi-engine execution | kısmi | route tuple, non-compositional execution |
| Completeness contract | kısmi | property execution telemetry |
| Provenance graph | kısmi | document/version/chunk IDs; transient claims |
| Query/execution trace | kısmi | QueryRun/steps/message metadata |

## Architecture pressure points

1. Regex/operation listeleri yeni doğal dil talepleriyle büyüyor.
2. `QueryPlan.operation` ile `RouteSelection.intent` kısmen çakışıyor.
3. Logical request ve physical engine seçimi aynı orchestration katmanında karışıyor.
4. Property claim/provenance/dedup kavramları generic olmaya zorlanıyor fakat domain-specific.
5. Entity resolution top-k dışı enumeration ihtiyacı için entity store yerine kullanılamaz.
6. Top-k evidence ile exhaustive semantics ayrımı yalnızca property domaininde çözülmüş.
7. Graph concepts transient/upstream artifacts olarak kalıyor.
8. Temporal yorumlar planner/property regex/free-text metadata arasında dağılmış.
9. GraphRAG final answer common citation finalization'dan farklı davranıyor.
10. “Hybrid + GraphRAG” route etiketi gerçek composed execution değildir.

## Sahip kararı gerektiren açık sorular

* Canonical entity identity, alias, reindex ve workspace scope politikası nedir?
* Hangi sorgular corpus-complete sonuç garantisi istemelidir?
* Claim/fact/event/relation authoritative mi, reviewable projection mı olacaktır?
* Çelişen chunk, metadata, property claim ve GraphRAG bilgisinde provenance/truth politikası nedir?
* Document date, mention date, event date, range ve uncertainty için temporal model ne olmalıdır?
* Typed IR'da hangi operasyonlar bağlayıcıdır: LIST/COUNT/GROUP/RANK/COMPARE/traversal?
* Engine composition, readiness/cost/failure/citation kararlarını hangi execution policy verecektir?
* Cortex bağımsız graph/store sahibi olacak mı, GraphRAG'ın rolü ne olacaktır?
* “grounded”, “corpus-complete”, “partial” ve “unsupported” kullanıcı sözleşmesi nasıl ayrılacaktır?

