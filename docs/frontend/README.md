# Frontend Architecture

The application shell is Sidebar + (Header + Content), with a collapsed sidebar by default
and drawer behavior on narrow screens. Main V1 routes cover Dashboard, Workspaces, workspace
overview, Documents, document details/versions, upload/import, Chat, Conversations,
Processes, failed-job diagnostics, Graph explorer, System map, Settings, provider/model
settings, appearance settings, canonical Knowledge curation, and Health/status.
The expanded sidebar owns the active workspace selection for workspace-scoped pages. The
selection is persisted in browser localStorage and restored when the platform starts; if the
stored workspace is unavailable, the first available workspace becomes active.

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

The System Map assigns every node a semantic color and keeps React Flow behind the Cortex-owned
canvas abstraction. The Live system and Background workflows tabs retain operational health and
durability views. The Query V2 and Indexing V2 tabs are generated from the exported
`SYSTEM_MAP_V2_MANIFEST`: every visual group names one real implementation boundary, canonical
architecture document, and nearest scoped `AGENTS.md`/`CLAUDE.md` context. Selecting a node opens
description, boundary, guarantee, documentation, and AI-context detail tabs.

Query V2 shows Conversation Context → Query Understanding → Query IR → Execution Planning.
Execution Planning is a separate parent for Structured Query, Knowledge Graph, Retrieval, and
GraphRAG. All four converge through Result & Evidence before Reasoning & Composition and Answer.
GraphRAG is explicitly non-final and separate from canonical Knowledge Graph execution.

Indexing V2 shows Source Processing, Document Structure, Entity/Mention, Identity, Relation,
Event, Temporal, Claim/Fact, and canonical KG Build, followed by separate BM25, Dense/Qdrant, and
GraphRAG projections converging at Generation/Readiness. The map describes implemented boundaries
without claiming Phase 13 runtime activation or full-corpus completeness.

The layout rule retains a 205 px node width, 160 px minimum node height, 100 px horizontal and
80 px vertical inner padding, and a minimum 100 px node gap. Edge labels use opaque backgrounds,
and persistent-store nodes retain the dedicated slate presentation.

The Graph explorer is separate from the System map: it selects a workspace, reports the
GraphRAG state, queues its durable reindex workflow on explicit user action, and renders the
bounded entity/relationship projection returned by the workspace-scoped graph endpoint. Its
compact circular entity cards use a 108 px width and height with translucent semantic-color
backgrounds, arranged in a staggered honeycomb grid;
their type badges map to the input, service, retrieval, processing, local-model, decision, or
persistent-data palette. Selecting a card toggles a small description tooltip, keeping the
canvas readable while preserving the entity detail. The compact legend uses the same colors,
and relationship labels retain opaque backgrounds on dashed Bezier edges.
The Canonical Knowledge page is also separate from the extracted Graph explorer. It uses generated
OpenAPI types to list canonical entities, inspect exact-span mention evidence, add or tombstone
aliases, merge identities, partition all active mentions during split, and review lossless identity
history. Every mutation requires a visible reason and remains scoped to the selected workspace.
The Processes page renders the full versioned workflow schema for the selected run, including
steps that have not yet persisted a checkpoint; live SQLite/SSE step states are overlaid on
those nodes so queued runs remain understandable from their first event. `workflowSchemas.ts`
is the shared frontend definition for the System map and Processes page; it records each
checkpoint's purpose, technology boundary, and operational guarantee.

Workflow-event-triggered list refreshes are coalesced briefly, so a burst of SSE events does not
rebuild the process canvas for every individual event. The page also shows whether its SSE stream
is live, connecting, or reconnecting, the last successful SQLite status check, and the selected
run's last persisted state change. A manual refresh remains available when an operator needs to
distinguish a long-running stage from a disconnected browser session.

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

`AToastProvider` is mounted once at the application root and owns transient, accessible
operation feedback. The API client reports every mutating REST request through this Cortex-owned
adapter: successful commands receive a concise success message and failed requests show the
sanitized server or connection message. React feature code may use `useToast` for feedback that
does not originate from an API request; it must not import PrimeReact Toast directly.
The provider also reports uncaught browser errors and unhandled promise rejections, while
`AErrorBoundary` keeps a render failure visible and supplies the same sanitized feedback. Equal
error notifications are coalesced for three seconds to prevent polling or retry loops from
flooding the interface.

Playwright tests in `frontend/e2e` exercise the running Compose frontend through the browser;
the test suite requires the Chromium browser installed by Playwright.
