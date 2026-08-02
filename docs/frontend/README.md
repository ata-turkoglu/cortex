# Frontend Architecture

The application shell is Sidebar + (Header + Content), with a collapsed sidebar by default
and drawer behavior on narrow screens. Main V1 routes cover Dashboard, Workspaces, workspace
overview, Documents, document details/versions, upload/import, Chat, Conversations,
Processes, failed-job diagnostics, Graph explorer, System map, Settings, provider/model
settings, appearance settings, and Health/status.

PrimeReact, lucide-react, and React Flow stay behind typed Cortex-owned abstractions.
Feature code imports only those abstractions and the generated OpenAPI client.
