# ai-harness — operator rules

## Autonomy scope

- Agents MAY `git commit`, `git push`, and deploy **only within this repo**.
- Global user rules still apply outside this repo.
- Kill-switch: set repo variable `PAUSE_AGENTS=true` to halt every workflow.

## Branch protection — DISABLED (private repo on free plan)

Branch protection requires GitHub Pro ($4/mo) for private repos. The repo was switched to private 2026-04-14; protection is silently off. Direct pushes to `main` still work. Relevant implications:

- **CI + reviewer still run** on PRs; their success/failure is visible in the PR UI but not enforced.
- **Risk:** anyone with write access can push broken code to `main`. For a solo lab this is fine.
- **To re-enable:** pay for GH Pro or switch repo back to public.

Previously-listed required checks (for documentation when you upgrade): `ci / python`, `ci / web`, `ci / e2e`, `ci / docker`, `reviewer / review (quality)`, `reviewer / review (security)`, `reviewer / review (deps)`.

## Feature intake: `agent:build` label — **REQUIRES ANTHROPIC_API_KEY**

- Open a GitHub issue describing what you want.
- Apply the `agent:build` label.
- `planner.yml` fires → `agents/planner.py` runs Claude Opus with `Read`/`Write`/`Edit` filesystem tools.
- Planner opens a PR on a `feat/<issue>-<slug>` branch, referencing the issue.
- PR goes through CI + 3-pass reviewer + 1 human approval, then merges.

If planner makes no changes, it posts its plan summary as an issue comment instead.

Kill-switch: `PAUSE_AGENTS=true` halts planner workflows.

### Planner backend

The planner now runs on GitHub Models free tier by default (`HARNESS_BACKEND=github_models`). It uses a minimal tool-use loop implemented in `agents/src/agents/lib/github_models.py` that maps OpenAI tool calls to local file operations (Read/Write/Edit/Glob/Grep).

Tool execution is sandboxed — paths are restricted to the checked-out repo; no Bash, no network, no arbitrary Python. Watch for the `models:read` permission in `planner.yml`.

If you prefer Anthropic (better quality for complex tasks): `gh secret set ANTHROPIC_API_KEY --body sk-ant-...` and set `HARNESS_BACKEND=anthropic` as a repo var or in the workflow env.

## Autonomous product loop (P50–P52)

Three new moving parts close the full self-directing cycle:

1. **`product-manager.yml`** — cron 06/12/18 UTC + `workflow_dispatch`. Reads `docs/product/vision.md` + `docs/product/state.yaml` + currently-open `agent:build` issues. If vision is empty or >= `max_open_agent_issues` are open, exits with `pm: skipped`. Otherwise picks the top backlog item (or generates a new one), opens a GH issue with `agent:build`, and moves the item to `in_progress` in state.yaml. Commits state.yaml with `[skip ci]`.
2. **`product-analyzer.yml`** — triggered by `workflow_run: release-notes`. Reads the last 50 merged commits + vision + state. Moves items from `in_progress` → `shipped` when a matching commit is found; appends up to 3 new backlog items (LLM-proposed) grounded in vision. Commits state.yaml with `[skip ci]`.
3. **Triager + deployer auto-label** — issues created by `triager.py` (severity ≥ important) and all regression issues from `deployer.py` now include `agent:build`, so the planner fires without human intervention.

### Seeding the loop

1. Edit `docs/product/vision.md` once — fill in "What are we building?" and "Out of scope". The PM agent refuses to act on an empty vision.
2. Optionally seed `docs/product/state.yaml` with 2–3 backlog items you want built first. If unset, the PM agent will propose its own.
3. `gh workflow run product-manager.yml` to run it immediately (otherwise it fires at 06/12/18 UTC daily).

### Guardrails in place

- `max_open_agent_issues` in state.yaml throttles the PM (default 2) so planner never stacks more than N PRs.
- `deploy-prod.yml` has `paths-ignore: [docs/product/**, docs/superpowers/**, RELEASES.md, *.md]` — markdown-only commits don't deploy.
- Both PM and Analyzer commits use `[skip ci]` as belt-and-suspenders.
- Kill switch: `gh variable set PAUSE_AGENTS --body true` halts all autonomous workflows.

## Planner reliability (P60)

Three improvements cut planner PR bugs:

1. **Explicit repo conventions in `planner.md`** — before/after import examples show the LLM that `from api.main import app` is correct, not `from apps.api.src.api import app`. Lists test-file locations, router wiring, and files the planner must NEVER edit.
2. **Pre-commit validation in `planner.py`** — after the LLM tool loop, run `ruff check` + `python -m compileall` + `pytest` on the changed files. On failure, feed errors back to the LLM for ONE retry. If the retry still fails, post a comment on the issue explaining the failure and skip the PR (no branch pushed).
3. **`pull_request_target` trigger on CI + reviewer** — bypasses GitHub's cascade protection so planner-opened PRs run the same CI + 3-pass review gates as human-opened ones. **Security caveat:** `pull_request_target` runs with base-branch secrets (e.g. ANTHROPIC_API_KEY for reviewer). Under this trigger, a malicious PR could theoretically modify `uv.lock`/`pnpm-lock.yaml` to pull a poisoned package whose install script runs with those secrets. Acceptable here because the repo is private and only Dependabot (trusted GitHub-managed) + the owner's own agents open PRs. If external contributors are ever enabled, switch to one of: (a) install deps from base SHA then only read source from PR head, (b) use a dedicated bot PAT on the planner so CI still fires on `pull_request` events, or (c) require manual `workflow_dispatch` for review on external PRs. Do NOT merge external PRs without addressing this first.

## Full loop (P70)

After P60 + auto-fix + auto-merge, the chain runs unattended:

1. PM cron fires (06/12/18 UTC) → picks backlog item → opens issue with `agent:build` label
2. Planner fires on `issues.opened` → writes code → runs `ruff --fix --unsafe-fixes` on touched files → validates (ruff/compile/pytest) → retries once on failure → opens PR → queues `gh pr merge --auto --squash --delete-branch`
3. CI runs (ruff/mypy/pytest/vitest/playwright/docker) + Reviewer posts 3 commit statuses
4. All checks green → GitHub auto-merges + deletes the branch
5. `deploy-prod.yml` fires on push to main → Railway deploys
6. `rollback-watch` + `release-notes` + `product-analyzer` all cascade on `workflow_run`
7. Analyzer moves the item to `state.shipped`, opens next PM slot
8. Next cron tick → loop

Kill-switch for auto-merge: `AUTO_MERGE=false` env var on `planner.yml`, OR manually `gh pr merge <N> --disable-auto` on any specific PR in flight.

Safety net: P60 validation gate runs locally before the PR opens, so broken code never reaches GitHub. If it somehow does, CI catches it (auto-merge waits); if it STILL somehow ships, `rollback-watch` detects post-deploy error spikes and can `git revert` with `AUTO_ROLLBACK=true`.

## Secrets

Stored as repo secrets:

| Secret | Used by | Phase added |
|---|---|---|
| `RAILWAY_TOKEN` | deploy-prod.yml | 1 |
| `RAILWAY_DEV_TOKEN` | deploy-dev.yml | P3 |
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
- `SENTRY_REGION` repo variable — set to `de` for EU-residency Sentry accounts (API base becomes `https://de.sentry.io/api/0`). Leave unset for US default.

When unset, the watcher exits 0 silently (no false alerts before Sentry is wired).

Auto-rollback (`git revert` or Railway rollback) is **not** in Phase 5 — it's alert-only. Add auto-revert when the alert pipeline proves reliable.

**Auto-revert:** set Railway env `AUTO_ROLLBACK=true` and rollback-watch will also `git revert <bad_sha>` + push, triggering a new deploy of the previous state. Default off (alert-only).

## Triager (nightly self-healing)

`triager.yml` runs at 09:00 UTC daily (and on `workflow_dispatch`). It:

1. Pulls the last 24h of Sentry-grouped issues
2. For each, checks if a GH issue with marker `<sentry-issue-id>{id}</sentry-issue-id>` already exists (open or closed → dedupe)
3. Creates new GH issues with labels `bug`, `autotriage` and a Sentry permalink in the body

To enable, populate:
- `SENTRY_AUTH_TOKEN` secret
- `SENTRY_ORG_SLUG` / `SENTRY_PROJECT_SLUG` repo variables

Without these, the triager exits 0 silently.

**Regression detection:** when a Sentry issue ID matches a CLOSED GH issue, triager reopens it with label `regression` instead of creating a duplicate. This closes the self-healing loop for recurring bugs.

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

## Backend selection: Anthropic vs GitHub Models

By default agents use `claude-agent-sdk` (requires `ANTHROPIC_API_KEY`). To switch to GitHub Models free tier:

```bash
export HARNESS_BACKEND=github_models
# uses GITHUB_TOKEN by default; or set a dedicated token:
export GITHUB_MODELS_TOKEN=<your token with models:read scope>
# default model is openai/gpt-4o-mini; override:
export GITHUB_MODELS_MODEL=openai/gpt-5
```

Set the same env on Railway / GH Actions secrets to use GH Models in production.

**Limitation:** GH Models backend does NOT support tools (Read/Write/Edit/Glob/Grep). The planner agent (which writes code) will raise NotImplementedError under this backend. All other agents (reviewer, triager, healthcheck, release-notes, pr-describer, issue-labeler) work fine — they're text-in, text-out.

GH Models free-tier rate limits: ~50 premium-model requests/day; faster for non-premium. Sufficient for a solo lab.

## Multi-environment pipeline (Phase P3)

6-phase flow:

1. **Verify CI** — `ci.yml` on PR (ruff/mypy/pytest/vitest/playwright/docker/env-parity)
2. **Deploy Dev** — `deploy-dev.yml` on push to main → Railway `ai-harness-dev`
3. **Test Dev** — `test-dev.yml` post-deploy → Playwright smoke against dev URL
4. **Deploy Prod** — `deploy-prod.yml` on push to main → Railway `ai-harness` (currently independent of test-dev; when you want dev-gating, add `workflow_run: [test-dev]` trigger to deploy-prod.yml)
5. **Test Prod** — `test-prod.yml` post-deploy → `/api/ping` smoke
6. **Release** — `release-notes.yml` gated on `deploy-prod` success → AI-generated CHANGELOG + GH Release

Parallel to 4–6: `rollback-watch.yml` fires after `deploy-prod` and watches Sentry for 10 min.

### Required config

- Secret `RAILWAY_DEV_TOKEN` — deploy token for the dev Railway service
- Variable `RAILWAY_DEV_SERVICE` (optional; defaults to `ai-harness-dev`)
- Variable `DEV_URL` (optional; defaults to `https://ai-harness-dev-production.up.railway.app`)
- Variable `PROD_URL` (optional; defaults to `https://ai-harness-production.up.railway.app`)

**Dev pipeline workflows are DISABLED** until the user creates the Railway dev service + `RAILWAY_DEV_TOKEN` secret. To enable after setup:

```bash
gh workflow enable deploy-dev.yml --repo nt-suuri/ai-harness
gh workflow enable test-dev.yml --repo nt-suuri/ai-harness
gh secret set RAILWAY_DEV_TOKEN --repo nt-suuri/ai-harness --body <railway-dev-token>
```

Then optionally add `workflow_run: [test-dev]` trigger to `deploy-prod.yml` for dev-gating.

## Activation state (2026-04-14)

- **Live via GitHub Models free tier:** reviewer, release-notes, triager, healthcheck, pr-describer, issue-labeler
  - Each workflow has `models: read` permission + `HARNESS_BACKEND=github_models` env
  - Uses the built-in `GITHUB_TOKEN` — no PAT needed
  - Rate limits: ~50 premium-model requests/day (GH Models free tier)
- **Anthropic-required (awaiting `ANTHROPIC_API_KEY` secret):** planner
  - The planner uses Read/Write/Edit filesystem tools; GH Models doesn't expose those yet
