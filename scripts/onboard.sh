#!/usr/bin/env bash
# Interactive setup walkthrough for a fresh ai-harness fork.
#
# Idempotent: re-runs are safe; existing config is preserved.
# Usage: ./scripts/onboard.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
green() { printf "\033[0;32m%s\033[0m\n" "$1"; }
red() { printf "\033[0;31m%s\033[0m\n" "$1"; }
yellow() { printf "\033[0;33m%s\033[0m\n" "$1"; }
ask() {
  local prompt="$1"
  local default="${2:-}"
  local answer
  if [ -n "$default" ]; then
    read -r -p "  $prompt [$default]: " answer
    echo "${answer:-$default}"
  else
    read -r -p "  $prompt: " answer
    echo "$answer"
  fi
}
confirm() {
  local prompt="$1"
  local answer
  read -r -p "  $prompt [y/N]: " answer
  case "${answer,,}" in
    y|yes) return 0 ;;
    *) return 1 ;;
  esac
}

bold "ai-harness — onboard walkthrough"
echo "Repo root: $REPO_ROOT"
echo

# ─── Tool checks ─────────────────────────────────────────────────────────
bold "1. Tool checks"
for tool in git uv pnpm gh; do
  if command -v "$tool" >/dev/null 2>&1; then
    green "  ✓ $tool ($(command -v "$tool"))"
  else
    red "  ✗ $tool — install it (https://docs.astral.sh/uv/, https://pnpm.io/, https://cli.github.com/)"
    MISSING_TOOLS=true
  fi
done
[ -n "${MISSING_TOOLS:-}" ] && { red "Install missing tools and re-run."; exit 1; }

# Optional: railway
if command -v railway >/dev/null 2>&1; then
  green "  ✓ railway (optional, for deploy)"
else
  yellow "  ! railway CLI missing — install via 'brew install railway' or 'npm i -g @railway/cli' if you want deploy"
fi
echo

# ─── GitHub auth ─────────────────────────────────────────────────────────
bold "2. GitHub auth"
if gh auth status >/dev/null 2>&1; then
  green "  ✓ gh authenticated as $(gh api user -q .login)"
else
  yellow "  Not authenticated. Run: gh auth login"
  exit 1
fi

REPO=$(ask "Repo (owner/name)" "$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo '')")
if [ -z "$REPO" ]; then
  red "  Repo required."
  exit 1
fi
green "  Using repo: $REPO"
echo

# ─── Install deps ────────────────────────────────────────────────────────
bold "3. Install dependencies"
echo "  uv sync --group dev --all-packages"
uv sync --group dev --all-packages
echo "  pnpm install"
pnpm install
green "  ✓ deps installed"
echo

# ─── Pre-commit ──────────────────────────────────────────────────────────
bold "4. Pre-commit hooks"
if [ -f ".git/hooks/pre-commit" ]; then
  green "  ✓ already installed"
else
  if confirm "Install pre-commit hooks (recommended)?"; then
    uv run pre-commit install
    green "  ✓ installed"
  fi
fi
echo

# ─── Repo variables ──────────────────────────────────────────────────────
bold "5. Repo variables"
if gh variable list --repo "$REPO" --json name -q '.[].name' | grep -q '^PAUSE_AGENTS$'; then
  green "  ✓ PAUSE_AGENTS exists"
else
  if confirm "Create PAUSE_AGENTS variable (empty = unpaused)?"; then
    gh variable set PAUSE_AGENTS --repo "$REPO" --body " "
    green "  ✓ created"
  fi
fi
echo

# ─── Secrets ─────────────────────────────────────────────────────────────
bold "6. Secrets (paste interactively; nothing is logged)"
EXISTING_SECRETS=$(gh secret list --repo "$REPO" --json name -q '.[].name')

for secret in RAILWAY_TOKEN ANTHROPIC_API_KEY SENTRY_AUTH_TOKEN RESEND_API_KEY; do
  if echo "$EXISTING_SECRETS" | grep -q "^$secret$"; then
    green "  ✓ $secret already set"
  else
    if confirm "Set $secret now?"; then
      read -r -s -p "    paste value: " value
      echo
      if [ -n "$value" ]; then
        printf "%s" "$value" | gh secret set "$secret" --repo "$REPO" --body -
        green "    ✓ $secret set"
      else
        yellow "    skipped (empty)"
      fi
    fi
  fi
done
echo

# ─── Verify ──────────────────────────────────────────────────────────────
bold "7. Verify"
if uv run harness doctor 2>&1; then
  green "  ✓ harness doctor green"
else
  yellow "  ! harness doctor reported issues — review above"
fi
echo

bold "Done."
echo "Next:"
echo "  - 'uv run harness verify' to live-check the deployed app"
echo "  - 'uv run harness pause / resume' to halt or resume agents"
echo "  - Open an issue + apply the 'agent:build' label to invoke the planner"
