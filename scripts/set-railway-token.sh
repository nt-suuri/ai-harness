#!/usr/bin/env bash
# Helper: set RAILWAY_TOKEN GitHub secret from a token the user pastes.
# Usage: ./scripts/set-railway-token.sh <token>
#   or:  echo <token> | ./scripts/set-railway-token.sh -

set -euo pipefail

REPO="nt-suuri/ai-harness"

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <token> | $0 -   (read from stdin)"
  exit 1
fi

if [ "$1" = "-" ]; then
  TOKEN=$(cat)
else
  TOKEN="$1"
fi

if [ -z "$TOKEN" ]; then
  echo "Error: empty token"
  exit 1
fi

echo "$TOKEN" | gh secret set RAILWAY_TOKEN --repo "$REPO" --body -
echo "✅ RAILWAY_TOKEN set on $REPO"
gh secret list --repo "$REPO" | grep RAILWAY
