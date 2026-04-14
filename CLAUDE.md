# ai-harness — operator rules

## Autonomy scope

- Agents MAY `git commit`, `git push`, and deploy **only within this repo**.
- Global user rules still apply outside this repo.
- Kill-switch: set repo variable `PAUSE_AGENTS=true` to halt every workflow.

## Branch protection (must be configured on GitHub)

- `main` is protected.
- Required checks: `ci / python`, `ci / web`, `ci / e2e`, `ci / docker`, `reviewer / review (quality)`, `reviewer / review (security)`, `reviewer / review (deps)`.
- Require 1 human approval. No force-push. No direct push to `main`.

## Feature intake: `agent:build` label

- Open a GitHub issue describing what you want.
- Apply the `agent:build` label.
- `planner.yml` fires → `agents/planner.py` runs Opus 4.6 with filesystem tools.
- Planner opens a PR on a `feat/<issue>-<slug>` branch, referencing the issue.
- PR goes through CI + 3-pass reviewer + 1 human approval, then merges.

If planner makes no changes, it posts its plan summary as an issue comment instead.

Kill-switch: `PAUSE_AGENTS=true` halts planner workflows.

## Secrets

Stored as repo secrets:

| Secret | Used by | Phase added |
|---|---|---|
| `RAILWAY_TOKEN` | deploy.yml | 1 |
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
