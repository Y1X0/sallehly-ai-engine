# apps/web-dashboard

**Responsibility:** the user-facing product — brief submission, storyboard
review/approval (the human checkpoint before any full-cost render),
render progress, gallery, billing.

**Planned stack:** Next.js + TypeScript + Tailwind, WebSocket subscription
to job progress via `apps/api`.

**Status:** Phase 6 target. Not scaffolded yet — Phase 0-5 are all
backend/pipeline foundation, and building the frontend before the API
contracts it depends on are stable would create rework. See
`docs/api/openapi.yaml` for the contract it will be built against.
