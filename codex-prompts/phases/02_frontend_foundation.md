# Phase 2 — Frontend Foundation

## Goal

Create the React application shell, UI abstraction layer, appearance system, and platform layout.

## Checklist

- [x] Create React + Vite + TypeScript application.
- [x] Configure Tailwind CSS.
- [x] Configure PrimeReact through a dedicated adapter/theme layer.
- [x] Configure React Router.
- [x] Configure Zustand.
- [x] Configure TanStack Query.
- [x] Configure React Hook Form and Zod.
- [x] Configure React Flow through Cortex abstractions.
- [x] Create the icon registry and `AIcon`.
- [x] Create `AInfo`.
- [x] Create `AButton`, `ADialog`, `ATable`, and the required main abstraction components.
- [x] Prevent direct PrimeReact imports outside the UI layer through lint rules or architecture tests.
- [x] Prevent direct lucide-react imports outside the icon layer.
- [x] Create `APlatformLayout`.
- [x] Create sidebar collapsed by default.
- [x] Create header toggle button.
- [x] Create icon-only collapsed navigation with tooltips.
- [x] Create mobile drawer behavior.
- [x] Create header background activity bar.
- [x] Create global active-job indicator.
- [x] Create system-health indicator.
- [x] Create content layout and route placeholders.
- [x] Add Appearance Settings state and theme provider.
- [x] Add light/dark/system handling.
- [x] Add PrimeReact preset, primary color, surface palette, radius, density, font scale, and animations.
- [x] Add component tests for key abstractions.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] Feature pages contain no direct PrimeReact imports.
- [x] Feature pages contain no direct lucide-react imports.
- [x] Sidebar is collapsed on first load.
- [x] Header progress area can represent zero, one, or multiple jobs.
- [x] Theme settings visibly affect the application.
- [x] Frontend type checking and tests pass.

## Additional checklist

- [x] Create route placeholders for all V1 pages.
- [x] Add generated OpenAPI client integration boundary.
- [x] Prevent manual duplication of backend DTOs in feature code.
- [x] Add server-side pagination patterns for large tables.
- [x] Add virtualization abstractions for long lists where appropriate.
- [x] Add responsive-performance checks while background jobs are active.

## Additional checklist — onboarding and cost UI

- [x] Create first-run setup wizard UI.
- [x] Create provider configured/not-configured states without exposing secrets.
- [x] Create cost summary and budget-warning UI primitives.
- [x] Add GraphRAG cost/confirmation dialog.
- [x] Add Windows path selection and validation UI.
