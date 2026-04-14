# ai-harness

Solo 24/7 AI development harness. See `docs/superpowers/plans/` for phase plans and
`/Users/nt-suuri/.claude/plans/structured-whistling-thompson.md` for the master spec.

## Quickstart

```bash
uv sync
pnpm install
uv run pytest
pnpm -r test
```

## Layout

- `apps/api` — FastAPI backend
- `apps/web` — Vite + React frontend
- `agents/` — Python agents (added in Phase 2+)
- `.github/workflows/` — CI + deploy
