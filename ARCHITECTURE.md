# Architecture

The ai-harness implements the **plan → build → review → deploy → monitor → triage → fix → release** loop with AI agents at each step and the human gating only the final merge.

## The full loop

```
                ┌──────────────────────────────────────────────────────┐
                │                                                      │
                │   ┌─────────┐                                        │
                │   │  HUMAN  │                                        │
                │   └────┬────┘                                        │
                │        │ open issue                                  │
                │        │ (or auto-created by triager)                │
                │        ▼                                             │
                │   ┌─────────┐  agent:build label   ┌──────────────┐  │
                │   │  ISSUE  ├──────────────────────►│  PLANNER.py  │  │
                │   └─────────┘                       │ (Opus 4.6)   │  │
                │                                     └──────┬───────┘  │
                │                                            │          │
                │                                            ▼          │
                │                                       opens PR        │
                │                                            │          │
                │   ┌──────────────┐                         ▼          │
                │   │ ISSUE_LABELER├─────────────────►  ┌─────────┐     │
                │   │  (on open)   │                    │   PR    │     │
                │   └──────────────┘                    └────┬────┘     │
                │                                            │          │
                │                  ┌────────┬────────┬──────┴──────┐    │
                │                  │        │        │             │    │
                │   ┌──────────────▼──┐ ┌───▼────┐ ┌─▼────┐ ┌──────▼──┐ │
                │   │ PR_DESCRIBER    │ │ CI     │ │ ...  │ │REVIEWER │ │
                │   │ (auto-fill body)│ │ gate   │ │      │ │ × 3     │ │
                │   └─────────────────┘ └───┬────┘ │      │ │ (Opus)  │ │
                │                           │      │      │ └────┬────┘ │
                │                           ▼      ▼      ▼      ▼      │
                │                       ┌──────────────────────────┐    │
                │                       │  Branch protection gates │    │
                │                       │  (4 CI checks + 3 review │    │
                │                       │   + 1 human approval)    │    │
                │                       └──────────┬───────────────┘    │
                │                                  │ green              │
                │                                  ▼                    │
                │                           ┌────────────┐              │
                │                           │ HUMAN MERGE│              │
                │                           └────────┬───┘              │
                │                                    ▼                  │
                │                          push to main → DEPLOY        │
                │                          (Railway via deploy.yml)     │
                │                                    │                  │
                │                  ┌─────────────────┼─────────────────┐│
                │                  ▼                 ▼                 ▼│
                │            ┌──────────┐    ┌──────────────┐  ┌──────────────┐
                │            │ DEPLOYER │    │ROLLBACK-WATCH│  │RELEASE-NOTES │
                │            │ (no LLM) │    │ (Sentry rate)│  │ (Sonnet 4.6) │
                │            └──────────┘    └──────┬───────┘  └──────────────┘
                │                                   │ spike?       │
                │                                   ▼              ▼
                │                            ┌─────────────┐  CHANGELOG.md
                │                            │REGRESSION   │  + GH Release
                │                            │ ISSUE       │
                │                            └──────┬──────┘
                │                                   │
                │                                   │ also: Sentry events
                │                                   ▼
                │                            ┌─────────────┐
                │                            │  TRIAGER    │
                │                            │ (cron 09:00)│
                │                            │ Sonnet 4.6  │
                │                            └──────┬──────┘
                │                                   │ creates
                │                                   ▼
                └───────────────────────────────────┘
                         (loops back to ISSUE)
```

## Independent loops

Some workflows fire on schedule, not as part of the main loop:

| Workflow | Schedule | Purpose |
|---|---|---|
| `triager.yml` | Daily 09:00 UTC | Sentry issues → GH issues |
| `healthcheck.yml` | Daily 08:00 UTC | HEALTH dashboard issue + email |
| `stale.yml` | Weekly Sun 10:00 | Close inactive autotriage |
| `canary-replay.yml` | Weekly Sun 07:00 | Fixture replay through agent parsers |

## Invariants

These always hold regardless of which agents are running:

1. **Branch `main` is protected.** Direct push possible only with admin token (the bot has it for bootstrap; future development goes through PRs).
2. **Every workflow checks `PAUSE_AGENTS` first.** Setting that repo variable to `"true"` halts every agent immediately — first-step exit 0.
3. **No agent has admin scope.** Each workflow declares minimal `permissions:` block. Reviewer can comment + set status. Planner can write code + open PRs. Triager can create issues. None can delete things.
4. **Reviewer agents have `allowed_tools=[]`.** They can't take any side-effect action — only read the diff and emit a verdict line.
5. **Planner has filesystem tools but NOT Bash.** Code is written blind; CI validates. Reviewers + 1 human approval gate the merge.
6. **Deduplication is marker-based.** Triager embeds `<sentry-issue-id>{id}</sentry-issue-id>` in issue bodies; future runs grep for the marker.
7. **Idempotent agents.** Re-running any agent should produce the same outcome (or a no-op). Triager skips already-marked Sentry IDs. Stale closer skips fresh issues. Healthcheck appends a new section per day rather than rewriting.
8. **Dry-run mode for every agent.** `--dry-run` prints what would happen; no GH/Sentry/git side effects.

## State storage

The harness uses **GitHub itself** as primary storage:

- **Open issues** = current bug list / current dashboard
- **Closed issues** = history (preserved for triager regression detection)
- **PRs** = in-flight work
- **Workflow runs** = activity log
- **Repo variables** = config (PAUSE_AGENTS, RAILWAY_SERVICE)
- **Repo secrets** = credentials

Other state:

- **Sentry** is the source of truth for errors. Triager reads via API; never mirrors error data.
- **`agents/knowledge/known_false_positives.yaml`** — durable triager knowledge, version-controlled.
- **`actions/cache`** — per-agent scratch (e.g., processed Sentry fingerprints).
- **No database.** No Redis. No file-based persistent state on Railway (it scales to zero).

## Failure modes + mitigations

| Failure | Mitigation |
|---|---|
| Agent writes broken code | CI gate + 3-pass reviewer + 1 human approval |
| Bad deploy reaches prod | Rollback-watch detects Sentry spike, opens regression issue |
| Cascading triage spam | Marker-based dedup; stale closer cleans up after 14 days |
| Token leak in logs | Workflows use `secrets.X` (auto-masked); no `echo "$TOKEN"` |
| Prompt injection in issue body | Planner has no Bash; CI catches malicious code; humans gate merge |
| Prompt injection in PR diff | Reviewers have `allowed_tools=[]`; can only emit verdict; humans gate merge |
| Sentry DSN missing | Sentry init no-op; agents that need Sentry exit 0 silently |
| Anthropic API key missing | Workflow logs the failure; no other agents affected |
| Runaway agent | Per-agent turn cap (planner 80, others 20); workflow timeout-minutes |
| Stuck workflow | `harness pause` (or set PAUSE_AGENTS=true) halts everything |

## Module map

```
agents/src/agents/
├── __init__.py
├── cli.py                     # `harness` CLI (Click)
├── canary.py                  # weekly fixture replay
├── deployer.py                # post-deploy rollback watcher
├── healthcheck.py             # daily HEALTH issue + email
├── issue_labeler.py           # area:* + priority:* labels
├── planner.py                 # agent:build → PR
├── pr_describer.py            # auto-fill empty PR descriptions
├── release_notes.py           # post-deploy CHANGELOG + GH Release
├── reviewer.py                # 3-pass PR reviewer
├── stale.py                   # close inactive autotriage issues
├── triager.py                 # nightly Sentry → GH issues
└── lib/
    ├── anthropic.py           # claude-agent-sdk wrapper
    ├── email.py               # Resend wrapper
    ├── gh.py                  # PyGithub wrapper
    ├── kill_switch.py         # PAUSE_AGENTS check
    ├── prompts.py             # load named .md prompts
    ├── sentry.py              # Sentry REST client
    └── prompts/
        ├── healthcheck.md
        ├── issue_labeler.md
        ├── planner.md
        ├── pr_describer.md
        ├── release_notes.md
        ├── reviewer_deps.md
        ├── reviewer_quality.md
        ├── reviewer_security.md
        └── triager.md
```
