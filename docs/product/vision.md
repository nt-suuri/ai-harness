# Product Vision

## What are we building?

A self-operating software development harness. One human sets the vision; AI agents plan features, write code, review PRs, deploy to production, monitor for errors, and fix bugs — all autonomously. The dashboard at the root URL shows real-time CI/deploy stats and agent activity. The API exposes utility endpoints that the agents themselves build and maintain as demo features, proving the loop works end-to-end.

## Who is the user?

A solo developer who wants to see what a fully-automated AI engineering workflow looks like in practice. They interact primarily through the GitHub issue tracker (filing high-level requests) and the Railway-hosted dashboard (observing activity). They never write application code directly.

## Out of scope (negative constraints)

- Do not propose features outside the monorepo at `apps/api`, `apps/web`, or `agents/`.
- Do not propose anything requiring paid third-party services beyond Railway + GitHub.
- Do not propose features that require the user's manual data entry.
- Do not propose changes to the agent infrastructure itself (planner, reviewer, PM, analyzer, deployer, triager) — those are maintained by the human operator.
- Do not propose frontend frameworks or complex UI — the dashboard is intentionally minimal.
- Keep every feature small enough to ship in a single PR (1–3 files, under 50 lines).

## Current quarter focus

1. Build out the API with small, demonstrable utility endpoints that showcase the harness working.
2. Add basic observability features to the dashboard (latency, uptime, request counts).
3. Improve test coverage for existing API routes.
