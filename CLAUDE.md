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
uv run pre-commit install   # one-time: enable git pre-commit hooks
# api
uv run uvicorn api.main:app --reload --port 8080
# web
pnpm --filter web dev
```

## Rollback watch

After every deploy, `rollback-watch.yml` fires. It waits 10 min, queries Sentry for error counts, and opens a GitHub issue (labels: `regression`, `autotriage`) if:
- Post-deploy error rate > baseline × 3, AND
- Post-deploy count > 5 absolute

Triggers:
- `SENTRY_AUTH_TOKEN` secret — required for Sentry API
- `SENTRY_ORG_SLUG` / `SENTRY_PROJECT_SLUG` repo variables

When unset, the watcher exits 0 silently (no false alerts before Sentry is wired).

Auto-rollback (`git revert` or Railway rollback) is **not** in Phase 5 — it's alert-only. Add auto-revert when the alert pipeline proves reliable.

## Triager (nightly self-healing)

`triager.yml` runs at 09:00 UTC daily (and on `workflow_dispatch`). It:

1. Pulls the last 24h of Sentry-grouped issues
2. For each, checks if a GH issue with marker `<sentry-issue-id>{id}</sentry-issue-id>` already exists (open or closed → dedupe)
3. Creates new GH issues with labels `bug`, `autotriage` and a Sentry permalink in the body

To enable, populate:
- `SENTRY_AUTH_TOKEN` secret
- `SENTRY_ORG_SLUG` / `SENTRY_PROJECT_SLUG` repo variables

Without these, the triager exits 0 silently.

To trigger the loop manually: open the auto-created issue → add `agent:build` label → planner takes over.

## Healthcheck (daily)

`healthcheck.yml` runs at 08:00 UTC. Updates a pinned `HEALTH dashboard` issue (label: `healthcheck`) with yesterday's CI/deploy/Sentry counts. If `RESEND_API_KEY` secret + `HEALTHCHECK_TO_EMAIL` repo variable are set, also emails the same content.

## Canary replay (weekly)

`canary-replay.yml` runs Sundays at 07:00 UTC. Replays sanitized fixtures from `agents/tests/fixtures/` through `triager` parsers. Catches regressions in agent code. Fails if structural assertions break.

## Release notes (per deploy)

`release-notes.yml` runs after every successful deploy to main. It:

1. Lists commits since the last release tag
2. Asks Claude Sonnet 4.6 to write structured release notes
3. Prepends them to `RELEASES.md`, commits the file
4. Creates a tagged GitHub Release (`v{YYYY.MM.DD}-{HHMM}`)

Requires `ANTHROPIC_API_KEY` secret. Without it, the workflow fails at `run_agent`; the previous deploy is not affected.

## Stale issue closer (weekly)

`stale.yml` runs Sundays at 10:00 UTC. Closes any open issue with label `autotriage` whose `updated_at` is more than 14 days ago. Adds a comment explaining the close. The triager will reopen automatically if the underlying error recurs (Sentry id-based dedup).
