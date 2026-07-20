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

- `src/app/` - routes (App Router).
- `src/lib/apiClient.ts` - typed fetch wrapper for every `apps/api`
  endpoint (see `docs/api/openapi.yaml`).
- `src/lib/types.ts` - TypeScript types mirroring
  `packages/schemas/json/*.schema.json`.
- `src/lib/auth.tsx` - `AuthContext`/`useAuth`; bearer token in
  `localStorage`, attached as `Authorization: Bearer <token>`.
- `src/components/ui/` - the design system (buttons, cards, timeline,
  approval panels, status indicators) - reused across every page rather
  than styled ad hoc per page.

## Status (Phase 5)

Scaffolded via `create-next-app` (TypeScript, Tailwind, App Router, ESLint).
Pages/components/API integration land in the rest of Phase 5 - see the
root `README.md` roadmap section and `docs/adr/0011-frontend-and-auth.md`.
