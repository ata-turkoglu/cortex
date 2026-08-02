# Phase 2 — Frontend Foundation

## Goal

Create the React application shell, UI abstraction layer, appearance system, and platform layout.

## Checklist

- [ ] Create React + Vite + TypeScript application.
- [ ] Configure Tailwind CSS.
- [ ] Configure PrimeReact through a dedicated adapter/theme layer.
- [ ] Configure React Router.
- [ ] Configure Zustand.
- [ ] Configure TanStack Query.
- [ ] Configure React Hook Form and Zod.
- [ ] Configure React Flow through Cortex abstractions.
- [ ] Create the icon registry and `AIcon`.
- [ ] Create `AInfo`.
- [ ] Create `AButton`, `ADialog`, `ATable`, and the required main abstraction components.
- [ ] Prevent direct PrimeReact imports outside the UI layer through lint rules or architecture tests.
- [ ] Prevent direct lucide-react imports outside the icon layer.
- [ ] Create `APlatformLayout`.
- [ ] Create sidebar collapsed by default.
- [ ] Create header toggle button.
- [ ] Create icon-only collapsed navigation with tooltips.
- [ ] Create mobile drawer behavior.
- [ ] Create header background activity bar.
- [ ] Create global active-job indicator.
- [ ] Create system-health indicator.
- [ ] Create content layout and route placeholders.
- [ ] Add Appearance Settings state and theme provider.
- [ ] Add light/dark/system handling.
- [ ] Add PrimeReact preset, primary color, surface palette, radius, density, font scale, and animations.
- [ ] Add component tests for key abstractions.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] Feature pages contain no direct PrimeReact imports.
- [ ] Feature pages contain no direct lucide-react imports.
- [ ] Sidebar is collapsed on first load.
- [ ] Header progress area can represent zero, one, or multiple jobs.
- [ ] Theme settings visibly affect the application.
- [ ] Frontend type checking and tests pass.

## Additional checklist

- [ ] Create route placeholders for all V1 pages.
- [ ] Add generated OpenAPI client integration boundary.
- [ ] Prevent manual duplication of backend DTOs in feature code.
- [ ] Add server-side pagination patterns for large tables.
- [ ] Add virtualization abstractions for long lists where appropriate.
- [ ] Add responsive-performance checks while background jobs are active.

## Additional checklist — onboarding and cost UI

- [ ] Create first-run setup wizard UI.
- [ ] Create provider configured/not-configured states without exposing secrets.
- [ ] Create cost summary and budget-warning UI primitives.
- [ ] Add GraphRAG cost/confirmation dialog.
- [ ] Add Windows path selection and validation UI.
