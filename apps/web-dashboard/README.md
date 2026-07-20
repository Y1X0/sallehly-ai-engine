# apps/web-dashboard

**Responsibility:** the user-facing product — register/login, create a
project from a creative idea, review and approve/reject the storyboard
and render plan (the two human checkpoints from Phase 2/4), start
generation, watch job progress, and browse the asset library. This is a
product layer on top of `apps/api` - it never bypasses the backend or
re-implements pipeline logic (see `docs/api/openapi.yaml`).

**Stack:** Next.js 16 (App Router) + TypeScript + Tailwind CSS v4.

## Local development

```bash
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm install
npm run dev
```

Requires `apps/api` running separately (see `docs/DEV_SETUP.md`) - this
app makes real HTTP requests to it, never mocks the backend.

## Structure

- `src/app/` - routes (App Router): `/login`, `/` (dashboard), `/projects/[id]` (creative workspace).
- `src/lib/apiClient.ts` - typed fetch wrapper for every `apps/api`
  endpoint (see `docs/api/openapi.yaml`).
- `src/lib/types.ts` - TypeScript types mirroring
  `packages/schemas/json/*.schema.json`.
- `src/lib/auth.tsx` - `AuthContext`/`useAuth`; bearer token in
  `localStorage`, attached as `Authorization: Bearer <token>`.
- `src/components/ui/` - the design system (`Button`, `Card`,
  `StatusBadge`, `ProgressBar`, `Timeline`, `ApprovalPanel`, `ShotCard`) -
  reused across every page rather than styled ad hoc per page.
- `src/components/dashboard/` - project list + create-project form
  (incl. reference-image upload).
- `src/components/workspace/` - the creative workspace: scene timeline,
  storyboard/render-plan review (approval panels), generation jobs
  panel (with retry), asset library.

## Testing

- `npm test` - Vitest unit tests for the design system and `apiClient`.
- `npm run test:e2e` - Playwright, full lifecycle (register → create →
  plan → approve storyboard → approve render → generate → assets) plus
  auth/ownership checks, driven against real `uvicorn`/`next dev`
  servers in a real (pre-installed) Chromium.

## Status (Phase 5)

Implemented: login/register, project dashboard (list + create, incl.
reference-image upload), creative workspace (lifecycle timeline,
story/scene/shot cards, storyboard/render-plan approval with
reject-and-regenerate, real-time job status with retry, asset library).
See `docs/adr/0011-frontend-and-auth.md` for the design decisions,
including two real backend gaps (missing plan/storyboard/render-plan
GET endpoints, missing CORS policy) found and fixed while building this.
