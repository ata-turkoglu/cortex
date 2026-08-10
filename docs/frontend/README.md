# Frontend Architecture

The application shell is Sidebar + (Header + Content), with a collapsed sidebar by default
and drawer behavior on narrow screens. Main V1 routes cover Dashboard, Workspaces, workspace
overview, Documents, document details/versions, upload/import, Chat, Conversations,
Processes, failed-job diagnostics, Graph explorer, System map, Settings, provider/model
settings, appearance settings, and Health/status.

PrimeReact, lucide-react, and React Flow stay behind typed Cortex-owned abstractions.
Feature code imports only those abstractions and the generated OpenAPI client.
The reusable PrimeReact adapters live in `frontend/src/components/ui`, with one public
`A*` component per file. Feature code imports these components directly from that folder's
barrel export. Form labels use the Cortex-owned `ALabel` adapter with a consistent `grid gap-1`
layout; native file controls remain encapsulated inside `AFileUpload`.

`AConfirmationProvider` supplies the shared `useConfirmation` workflow for every destructive
or consequential action; browser-native confirmation prompts are not used in feature code.

The Chat page gives each new conversation a title derived from its first user question, and
backfills legacy placeholder titles when the history is loaded, keeping the persistent history
rail readable in a ChatGPT-style workflow. It presents workspace-scoped
citations as source actions. Selecting one opens a
Cortex-owned dialog with the cited chunk and its document-version number; source lookup is
performed with the active workspace ID so a citation cannot reveal another workspace's content.

`AServerTable` owns paged table controls and `AVirtualList` renders only a visible, overscanned
window of long lists. Feature code uses these Cortex-owned primitives rather than coupling to a
particular table or virtualization library.

The Appearance settings page is a PrimeReact theme builder. It loads one of the bundled
PrimeReact presets and applies persistent browser-local primary and secondary color tokens,
surface palette, density, typography scale, radius, and animation preferences. These are global
single-user presentation preferences; they are never workspace settings or server-stored data.

Model assignments are global and model discovery is capability-driven. One project-wide API
provider is selected with its credential; each layer then chooses either Local (installed Ollama
models) or that API provider, followed by a compatible model. The settings page can start a
user-requested Ollama model download and shows its progress; it never downloads models
automatically. API credentials are written to the host credential store through the validation
endpoint; they are never returned to the browser or included in global-settings responses.
The Ollama download dialog uses selectable rows with model descriptions and capabilities from the
official library catalogue rather than accepting an arbitrary free-text model name.
GraphRAG has independently selectable provider/model assignments for extraction, claim
extraction, community summaries, and Local, Global, and DRIFT search. It can use a local Ollama
model through its OpenAI-compatible endpoint or a configured OpenAI API model; entity and
relationship extraction deliberately share GraphRAG's one upstream extraction stage.
The default palette uses the subdued Nord blue (`#5e81ac`) and slate (`#4c566a`) tones, with
light panel surfaces and fine slate borders; the default PrimeReact preset is `saga-blue`, and
the same token system supplies its dark variant.

The System map assigns every node a semantic color. Its legend groups application flow, data and
retrieval, control, LLM source, and platform nodes; local and API LLM nodes remain visibly
distinct. The canvas uses labeled, color-coded background groups with solid boundaries for the
main flow stages; GraphRAG indexing is isolated from dense indexing in its own group, with a
minimum visual gap between adjacent nodes and stage boundaries; every node belongs to exactly
one stage group. The layout rule uses a 205 px node width, 160 px minimum node height, a
100 px horizontal gap, and an 80 px vertical gap: a next node starts only after the prior
node's right or bottom edge plus the matching-axis gap. Every group retains a 100 px
horizontal and 80 px vertical inner padding, while
selecting a node opens its contextual detail sidebar, which can be dismissed without changing
the active map. Persistent-store nodes use a dedicated slate color and a "Kalıcı kayıt" badge.
The query map uses separately spaced hybrid and GraphRAG lanes with Bezier edges to keep
route branches readable. Decision nodes render their positive and negative outcomes explicitly;
edge labels are concise and use an opaque background so they remain legible between nodes. The
document flow makes format-dependent behavior explicit: Markdown and plain
text are read directly as UTF-8, while PDF and DOCX pass through Docling (and its OCR path when
needed) before normalized Markdown is stored. Storage nodes explicitly mark both the persisted
record and its technology: source and normalized files use the workspace filesystem; document,
version, chunk, workflow-run, and checkpoint records use SQLite; dense vectors use Qdrant; sparse
corpora use workspace cache files; and canonical GraphRAG artifacts use workspace Parquet/JSON
files before their vector mirror is written to Qdrant.
For multi-document DOCX sources, the ingestion map includes Heading-2 normalization and
logical-boundary detection between the source version and chunking. It shows that every Markdown
`##` section becomes a `logical_documents` record, without archive-prefix matching, and that
chunks and GraphRAG inputs inherit those identities rather than only the DOCX filename.
The query flow likewise names the technology each branch reads from: SQLite for conversation,
citation, and telemetry records; Qdrant for dense vectors; workspace cache files for BM25S; and
GraphRAG Parquet/JSON artifacts plus their Qdrant mirror for graph routes.
Its planner also shows the `entity_document_lookup`/`needs_list` decision and the document-grouping
branch that deduplicates matching chunks into one result and citation per document. These are
internal stages of the existing query run, not separate background workflow checkpoints.

The Graph explorer is separate from the System map: it selects a workspace, reports the
GraphRAG state, queues its durable reindex workflow on explicit user action, and renders the
bounded entity/relationship projection returned by the workspace-scoped graph endpoint.
The Processes page renders the full versioned workflow schema for the selected run, including
steps that have not yet persisted a checkpoint; live SQLite/SSE step states are overlaid on
those nodes so queued runs remain understandable from their first event. `workflowSchemas.ts`
is the shared frontend definition for the System map and Processes page; it records each
checkpoint's purpose, technology boundary, and operational guarantee.

For GraphRAG, the Processes page also shows the upstream index pipeline's entity and relationship
extraction, description summarization, community-report, and embedding stages beneath the
durable `index` checkpoint. Microsoft GraphRAG currently exposes that pipeline as one CLI command,
so these child stages inherit the parent checkpoint state only while it is running or completed;
after an index failure they show as unverified rather than falsely claiming individual failure.
The process canvas uses the System map's semantic visual language: each node shows its
stage type, title, concise description, technology boundary, and a live state badge. Its compact
multi-row layout keeps GraphRAG's expanded pipeline readable without duplicating it below the flow.
After an upload, the Upload page lists each submitted filename with its ingestion checkpoints and
refreshes their workflow state until it reaches a terminal result; completed checkpoints use a
visible check mark.
Primary actions use the primary token as a filled button. Secondary actions use the same primary
token as outlined buttons, following the KnowledgeOS interaction hierarchy; danger coloring is
reserved for attention and error states.

Playwright tests in `frontend/e2e` exercise the running Compose frontend through the browser;
the test suite requires the Chromium browser installed by Playwright.
