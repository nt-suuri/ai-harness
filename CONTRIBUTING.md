# Contributing to ai-harness

This is a solo lab harness, but if you're forking it for your own use:

## Workflow

1. Open an issue describing the change.
2. If the change is trivial and you want to drive it: open a PR on a `feat/<issue>-<slug>` branch.
3. If you want the planner agent to attempt it: apply the `agent:build` label.
4. CI must be green. The 3-pass Claude reviewer (quality, security, deps) must approve.
5. Squash + merge.

## Local dev

See `README.md` Quickstart and `CLAUDE.md` Local dev.

## Code style

- Python: ruff (auto-fix) + mypy (strict). Pre-commit hooks enforce both.
- TypeScript: tsc strict, no eslint config (kept minimal — ruff equivalent for TS).
- Commit messages: conventional commits (`feat(scope): ...`, `fix(scope): ...`, `chore(scope): ...`, `docs(scope): ...`, `ci: ...`, `test(scope): ...`).

## Adding a new agent

1. Create `agents/src/agents/<name>.py` with a CLI matching the existing pattern (argparse, `--dry-run`, `--help-check-only`, `kill_switch.exit_if_paused()`).
2. Wire it into `agents/src/agents/cli.py` as a Click subcommand.
3. Create `.github/workflows/<name>.yml` with a kill-switch check as the first step.
4. Write tests in `agents/tests/test_<name>.py` — mock all external clients.
5. Update `README.md` and `CLAUDE.md` if it adds operator-visible behavior.
6. Document the phase plan in `docs/superpowers/plans/`.

## Tests

```bash
uv run pytest apps/api agents -v       # Python
pnpm --filter web test                  # JS unit
pnpm --filter web e2e                   # Playwright (auto-starts api)
```
