# ai-harness — operator rules

## Autonomy scope

- Agents MAY `git commit`, `git push`, and deploy **only within this repo**.
- Global user rules still apply outside this repo.
- Kill-switch: set repo variable `PAUSE_AGENTS=true` to halt every workflow.

## Branch protection (must be configured on GitHub)

- `main` is protected.
- Required checks: `ci / python`, `ci / web`, `ci / e2e`, `ci / docker`.
- Phase 3 will add `reviewer / quality`, `reviewer / security`, `reviewer / deps`.
- Require 1 human approval. No force-push. No direct push to `main`.

## Secrets

Stored as repo secrets:

| Secret | Used by | Phase added |
|---|---|---|
| `FLY_API_TOKEN` | deploy.yml | 1 |
| `ANTHROPIC_API_KEY` | all agents | 2 |
| `SENTRY_AUTH_TOKEN` | triager, healthcheck | 6 |
| `RESEND_API_KEY` | healthcheck | 7 |

## Local dev

```bash
uv sync --all-extras
pnpm install
# api
uv run uvicorn api.main:app --reload --port 8080
# web
pnpm --filter web dev
```
