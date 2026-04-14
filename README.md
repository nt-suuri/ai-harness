# ai-harness

[![ci](https://github.com/nt-suuri/ai-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/nt-suuri/ai-harness/actions/workflows/ci.yml)
[![deploy](https://github.com/nt-suuri/ai-harness/actions/workflows/deploy.yml/badge.svg)](https://github.com/nt-suuri/ai-harness/actions/workflows/deploy.yml)

Solo 24/7 AI development harness — implements the loop **plan → build → review → deploy → monitor → triage → fix → release** with AI doing 99% of the code and the human gating risk. Inspired by Peter Pang's CREAO writeup (April 2026).

Live at **<https://ai-harness-production.up.railway.app>** — `/api/ping` returns `pong`, `/` shows a status dashboard.

## What's in the box

| Layer | Component | Purpose |
|---|---|---|
| Target app | `apps/api` (FastAPI) + `apps/web` (Vite/React) | The thing the harness builds and deploys |
| Agent infra | `agents/lib/{anthropic,gh,sentry,kill_switch,prompts,email}.py` | Shared building blocks every agent uses |
| Reviewer | `agents/reviewer.py` + `reviewer.yml` | 3 parallel Claude passes (quality / security / deps) on every PR |
| Planner | `agents/planner.py` + `planner.yml` | Issues with `agent:build` label → Claude opens a PR |
| Triager | `agents/triager.py` + `triager.yml` | Nightly: Sentry events → dedupe → GitHub issues |
| Healthcheck | `agents/healthcheck.py` + `healthcheck.yml` | Daily summary issue + email digest |
| Deployer | `agents/deployer.py` + `rollback-watch.yml` | Post-deploy spike detection → regression issue |
| Stale closer | `agents/stale.py` + `stale.yml` | Weekly: close inactive autotriage issues |
| Release notes | `agents/release_notes.py` + `release-notes.yml` | After each deploy: AI-written CHANGELOG + GH Release |
| Canary replay | `agents/canary.py` + `canary-replay.yml` | Weekly: replay sanitized fixtures through agent parsers |
| Operator CLI | `harness <subcommand>` | Single entry point for all operations |

## Quickstart

```bash
uv sync --group dev --all-packages
pnpm install
uv run pre-commit install              # one-time

# Run all tests
uv run pytest apps/api agents
pnpm --filter web test

# Local dev
uv run uvicorn api.main:app --reload --port 8080   # api
pnpm --filter web dev                              # web (in another shell)
```

## Operator CLI

Once `uv sync` has run, the `harness` command is available:

```bash
harness status                          # CI/deploy/issue counts
harness review --pr 42 --pass quality   # invoke a single review pass
harness plan --issue 42                 # invoke planner against an issue
harness triage --dry-run                # see what triager would create
harness healthcheck --dry-run           # preview the daily digest
harness stale --stale-days 14           # close stale autotriage issues
harness release-notes --dry-run         # preview release notes
harness canary                          # run the fixture replay locally
harness pause                           # halt all agent workflows
harness resume                          # un-pause
harness doctor                          # check env health
harness logs --workflow ci.yml -n 5     # recent workflow runs
harness next-tag                        # show the tag release-notes would create
```

## Active vs awaiting-secrets

| Workflow | Status |
|---|---|
| `ci`, `deploy`, `rollback-watch`, `canary-replay`, `stale` | LIVE (no extra secrets needed) |
| `reviewer`, `planner`, `release-notes` | Code-complete; awaiting `ANTHROPIC_API_KEY` GH secret |
| `triager`, `healthcheck` (Sentry parts), `rollback-watch` (spike detection) | Awaiting `SENTRY_AUTH_TOKEN` secret + `SENTRY_ORG_SLUG` / `SENTRY_PROJECT_SLUG` repo vars |
| `healthcheck` (email digest) | Awaiting `RESEND_API_KEY` secret + `HEALTHCHECK_TO_EMAIL` repo var |

Kill switch: set repo variable `PAUSE_AGENTS=true` (or `harness pause`) to halt every agent workflow.

## Layout

```
ai-harness/
├── apps/
│   ├── api/         FastAPI backend
│   └── web/         Vite + React frontend (with Dashboard)
├── agents/
│   ├── src/agents/  Agent code + lib/
│   ├── tests/       Pytest + sanitized fixtures
│   └── knowledge/   Durable yaml (false-positive fingerprints)
├── .github/workflows/   11 workflows (CI, deploy, 8 agent workflows)
├── docs/superpowers/plans/   Phase-by-phase implementation plans
├── CLAUDE.md        Operator runbook
└── RELEASES.md      Auto-generated changelog
```

## Master spec

`/Users/nt-suuri/.claude/plans/structured-whistling-thompson.md` (lives outside the repo — it's the original brainstorm output).

## Phase log

The harness was built phase-by-phase across 14 phases:

1. **Foundation** — monorepo, FastAPI `/ping`, React, CI, Railway deploy
2. **Agent shared lib** — `agents/lib/` (anthropic, gh, sentry, kill_switch, prompts) + 6 stub prompts + knowledge yaml
3. **3-pass PR reviewer** — Claude reviews every PR (quality / security / deps)
4. **Autonomous planner** — `agent:build` label → Claude opens implementation PR
5. **Auto-deploy + rollback watch** — Sentry-based post-deploy spike detection, alert via GH issue
6. **Self-healing triager** — Nightly Sentry → GH issues with marker-based dedup
7. **Healthcheck + canary** — Daily HEALTH dashboard issue, weekly fixture replay
8. **Release notes** — Post-deploy: Claude writes CHANGELOG, creates GH Release
9. **Status dashboard** — `/api/status` endpoint + React component
10. **Stale issue closer** — Weekly: auto-close inactive autotriage issues
11. **`harness` CLI** — Click-based unified entry point
12. **CLI extras** — `doctor`, `logs`, `next-tag`
13. **Repo hygiene** — Issue templates, PR template, pre-commit hooks
14. **Docs** — This README
```
