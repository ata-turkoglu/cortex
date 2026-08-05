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

The Chat page presents workspace-scoped citations as source actions. Selecting one opens a
Cortex-owned dialog with the cited chunk and its document-version number; source lookup is
performed with the active workspace ID so a citation cannot reveal another workspace's content.

`AServerTable` owns paged table controls and `AVirtualList` renders only a visible, overscanned
window of long lists. Feature code uses these Cortex-owned primitives rather than coupling to a
particular table or virtualization library.

The Appearance settings page is a PrimeReact theme builder. It loads one of the bundled
PrimeReact presets and applies persistent browser-local primary and secondary color tokens,
surface palette, density, typography scale, radius, and animation preferences. These are global
single-user presentation preferences; they are never workspace settings or server-stored data.
The default palette uses the subdued Nord blue (`#5e81ac`) and slate (`#4c566a`) tones, with
light panel surfaces and fine slate borders; the default PrimeReact preset is `saga-blue`, and
the same token system supplies its dark variant.

Playwright tests in `frontend/e2e` exercise the running Compose frontend through the browser;
the test suite requires the Chromium browser installed by Playwright.
