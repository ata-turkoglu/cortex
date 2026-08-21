# Query Architecture V2: mevcut sorgu çalışma zamanı

> Bu paket mevcut durum araştırmasıdır; açıklayıcıdır, bağlayıcı hedef mimari değildir. İnceleme tarihi: 2026-08-16.

## Özet

Cortex V1, genel amaçlı semantik yürütme planlayıcısı değil, deterministik bir sohbet orkestratörüdür. Normal soru `backend/app/api/chat.py:query` ile alınır; `backend/app/chat/service.py:ask` kullanıcı mesajını, `QueryRun` ve üç `QueryStepRun` (`route`, `retrieve`, `synthesize`) kaydını oluşturur. Ardından iki ayrı karar yapılır:

* `chat/query_plan.py:plan_query()` operation, kişi bahsi, yıl kısıtı ve aggregation bayraklarını üretir.
* `chat/service.py:select_routes()` hybrid/GraphRAG yolu ve belge-listesi sunum niyetini seçer.

Bu iki model tek bir mantıksal/fiziksel plan değildir. `QueryPlan` property aggregation'a doğrudan yol açarken `RouteSelection` GraphRAG'a yol açar. LLM planlama çağrısı yoktur.

```
POST message
  → conversation doğrulama + Message(user) + QueryRun
  → QueryPlan + workspace-içi entity resolution + RouteSelection
  ├─ explicit property LIST/COUNT → active chunk scan → PropertyClaim → dedup → render
  ├─ GraphRAG route → durable worker job → native GraphRAG final answer
  └─ hybrid → Qdrant + BM25 → RRF → optional BGE → evidence selection
       → deterministic answer / optional committed-after OpenAI synthesis
  → citation finalization → Message(assistant) + trace metadata
```

## QueryPlan ve anlama davranışı

`QueryPlan` alanları: `operation` (`identify`, `describe`, `lookup_documents`, `list`, `count`, `timeline`, `compare`, `generic_qa`), `target`, `entities`, yıl tabanlı `DateConstraint`, `scope`, `retrieval_strategy`, exhaustive/aggregation/deduplication bayrakları, `aggregation_type`, reason code, confidence ve reason'dır. `QueryEntity` bahsi, NFC/casefold normalize biçimini, çözülmüş değeri, aliasları, adayları, confidence ve basis'i taşır.

Gerçek üretim değerleri regex ile belirlenir. Türkçe/İngilizce belge listeleme, property COUNT/LIST, dört haneli yıl, “kim”, “hakkında” kalıpları özeldir; diğerleri `generic_qa` olur. `compare` şemada vardır fakat planner üretmez. Sadece property için explicit envanter/sayı anlamı `requires_aggregation`, `requires_exhaustive_retrieval` ve `requires_deduplication` bayraklarını açar. `scope`, `retrieval_strategy`, `aggregation_type` ve bazı operation değerleri yürütmeyi doğrudan etkilemez.

Yalnızca `YYYY` veya `YYYY-YYYY` tanınır. Tam tarih, tarih aralığı, belge tarihi/event tarihi, grouping/ranking, genel LIST/COUNT, relation traversal ve entity enumeration için IR temsil yoktur. Şema doğrulaması Pydantic/JSON-LLM çıktısı veya repair/retry değil, Python dataclass/type düzeyindedir.

## Entity resolution

Uygulama-kanonik entity tablosu yoktur. `resolve_entities()` en fazla 5.000 aktif workspace chunk'ını ve `DocumentMetadata.value_json` değerini tarar; `_PERSON_NAME` ile çok-kelimeli kişi adayları çıkarır. Candidate score tam ad token desteği, belge/chunk sayısı, betimleyici legal/property bağlamı, metadata desteği ve numeric-OCR cezasından oluşur. Kazanan için skor >=0.72 ve ikinci adayla >=0.08 fark gerekir. Aksi halde çözüm yok/ambiguous kalır.

Honorific temizliği (`Dr.`, `Prof.` vb.) ve metin içinden aynı bahsin biçimlerini bulma dışında kalıcı alias çözümü yoktur. `Berke kim?` desteklenen bir tam ada çözülürse iyi çalışabilir; soyad-only, aynı adlı kişiler, kişiden farklı entity tipleri ve “tüm Merter'ler” için kanonik kimlik/alias/mention store bulunmadığından deterministik cevap verilemez. GraphRAG entities bu resolver tarafından kullanılmaz.

## Route ve engine yürütmesi

`select_routes()` document lookup için hybrid, `document_search` için hybrid, `deep_analysis`/`overview`/`pattern`/`across`/`genel`/`ilişki` için `("hybrid", "graphrag_global")` döndürür. Ancak `ask()` GraphRAG route varsa hybrid'i onunla birleştirmez: GraphRAG job kuyruğa alınır. `workflows/graphrag_query.py:execute()` graph ready kontrolü yapar, DB transaction dışında GraphRAG CLI çağırır ve native cevabı final olarak saklar. Yalnızca ayar ile açılan fallback GraphRAG başarısız olursa hybrid çalıştırır.

Normal hybrid sorgu `HybridRetrievalRuntime.search()` ile BM25 yükler, configured Ollama/OpenAI embedding üretir, workspace+embedding-hash filtresiyle dense arar, RRF uygular ve local BGE reranker kullanır. Dense/embedding/BM25/reranker hataları kontrollü partial/fallback davranışı üretir. Resolved tam adlar için ek, sınırlı retrieval query'leri yapılır. Document lookup sonuçları logical `document_id` ile gruplanır; bu exhaustive belge listesi değildir.

Property aggregation `aggregate_properties()` ile active document'ların active chunk'larını doğrudan SQL üzerinden tarar; top-k retrieval kullanılmaz. Bu route GraphRAG'ı kapatır. Aday keşfi, entity/alias substring'i ve property regex'i olduğundan `complete=True`, “aktif corpus üzerinde bu işlemin tamamlandığı” anlamındadır; gerçek dünya veya tüm entity/property doğruluğu değildir.

## Answer, citations ve trace

`Evidence` ortak source/content/score/document/version/chunk/citation/metadata taşıyıcısıdır. Normal cevapta deterministic evidence selector operation-aware seçim yapar. `_answer()` no-evidence için `unsupported`, aksi halde grounded/partial local fallback üretir. `execution.finalize_citations()` answer marker'larını doğrular, kullanılmayanları budar ve numaraları sıkıştırır. Assistant `metadata_json`; plan, route reason/confidence, entity resolution, retrieval/selection trace, citation summary, aggregation execution ve synthesis durumunu içerir. `/query-runs/{id}` debug endpointi bunların bir kısmını sunar.

OpenAI answer synthesis yalnızca ayar `answer_provider=openai` ise, evidence snapshot commit edildikten sonra çağrılır. Kopyalanmış ham evidence guard'ı ve bir regeneration denemesi vardır. GraphRAG native cevapları normal synthesis ve citation finalization yolunu bypass eder.

## Örnek soru davranışları

| Soru sınıfı | Mevcut temsil/yol | Beklenti |
|---|---|---|
| `Berke kim?` | identify → resolver → hybrid | kanıt varsa grounded, exhaustive değil |
| kişi hakkında | describe → hybrid | kanıt varsa özet |
| `Merter soyadlı kaç kişi?`, kimler? | generic QA → hybrid | entity inventory olmadığından exhaustive değil |
| soyada göre sayı / en çok 5 kişi | generic QA → hybrid | grouping/ranking desteklenmez |
| Hasan–Berke ilişkisi | çoğunlukla GraphRAG Global seçimi | native anlatı olabilir; relation query değil |
| `12.06.1974` ne oldu / tarihli belgeler | generic QA → hybrid | full-date filter veya event/document-date modeli yok |
| ölüm sonrası taşınmaz ilişkileri | describe veya broad GraphRAG | event+temporal+relation bileşimi yok |

