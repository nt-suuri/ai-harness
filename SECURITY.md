# Security

This is a solo lab harness. Security boundaries are intentionally minimal but explicit.

## Reporting

If you find something exploitable, open a private security advisory on the GitHub repo. Do not file public issues for security bugs.

## Threat model (non-exhaustive)

- **Prompt injection in PR diffs**: A malicious commit could embed instructions targeting the reviewer agent. Mitigation: reviewer's allowed_tools is `[]` — it can't take destructive actions even if jailbroken. Worst case: bogus VERDICT lines.
- **Prompt injection in issues**: Planner reads issue body. An adversarial issue could attempt to make the planner write malicious code. Mitigation: planner's allowed_tools excludes `Bash`; PR goes through 3-pass reviewer + 1 human approval.
- **Token exposure in workflow logs**: Every workflow uses `secrets.X` which GH Actions masks in logs. We never `echo "$TOKEN"`.
- **Sentry data leakage**: Sentry events may contain user PII. The triager only reads issue *titles* and counts — it does NOT read event payloads. The body it posts links back to Sentry rather than embedding the data.
- **Repo write scope**: Each workflow declares minimal `permissions:`. Reviewer gets `pull-requests:write + statuses:write`. Triager gets `issues:write`. Planner gets `contents:write + pull-requests:write + issues:write`. No agent has `admin`.

## Operator kill-switch

Run `harness pause` (sets `PAUSE_AGENTS=true` repo variable) to halt every agent workflow immediately. Every workflow checks this var as its first step and exits 0 if true.

## Secrets in this repo (none committed)

All secrets live in GH Actions repo secrets:
- `RAILWAY_TOKEN` — Railway deploy token
- `ANTHROPIC_API_KEY` — Anthropic API key (when set)
- `SENTRY_AUTH_TOKEN` — Sentry API token (when set)
- `RESEND_API_KEY` — Resend API key (when set)

`.env` files are gitignored. The `apps/api` Sentry init is DSN-optional (no-op if `SENTRY_DSN` unset).
