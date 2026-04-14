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

## Issue auto-labeler

`issue-labeler.yml` runs when a new issue is opened. An agent picks labels from a fixed allow-list (`area:api/web/agents/ci/docs`, `priority:high/low`) and applies them via gh. Skipped if the issue already has managed labels.

Allow-list lives in `agents/src/agents/issue_labeler.py:ALLOWED_LABELS`.

Requires `ANTHROPIC_API_KEY` secret.

## Stale issue closer (weekly)

`stale.yml` runs Sundays at 10:00 UTC. Closes any open issue with label `autotriage` whose `updated_at` is more than 14 days ago. Adds a comment explaining the close. The triager will reopen automatically if the underlying error recurs (Sentry id-based dedup).

## MCP server (operator from Claude Code)

`agents/src/agents/mcp_server.py` exposes 4 tools via MCP:
- `status` — same as `harness status`
- `triage_dry_run` — runs triager in dry-run; returns log lines
- `pause_agents` / `resume_agents` — toggles PAUSE_AGENTS

To register with Claude Code or Cursor, copy `.mcp/ai-harness.json` into the client's MCP config and reload. Then in your AI client: "use the ai-harness status tool".

The server runs over stdio — no port to expose, no auth needed.

## PR description auto-filler

`pr-describer.yml` runs when a PR is opened (event `pull_request.opened`). If the description is empty or under 60 characters, an agent reads the diff and asks Claude Sonnet 4.6 to write a structured description. Otherwise it's a no-op.

Requires `ANTHROPIC_API_KEY` secret.

## Security hardening (Phase 37)

- **Rate limit**: 60/min per IP on /api/*; 120/min on /api/ping (healthcheck). Returns 429 when exceeded.
- **Security headers**: every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security`, `Permissions-Policy: interest-cohort=()`.
- **Optional bearer auth** on `/api/status`, `/api/agents`, `/api/agents/*`: set env `STATUS_API_TOKEN` on Railway. When unset, endpoints stay open.
- **CORS**: env `CORS_ALLOWED_ORIGINS` (comma-separated). Empty (default) = same-origin only.
- **/api/status response cached 60 s** in-process — reduces GH API hits if endpoint gets hammered.
