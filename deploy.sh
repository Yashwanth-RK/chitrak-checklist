#!/usr/bin/env bash
# Deploy the Chitrak dashboard to Vercel.
#
# Needs a Vercel access token in VERCEL_TOKEN. Create one at
#   https://vercel.com/account/tokens
# The token is read from the environment and never written to disk.
set -euo pipefail

if [ -z "${VERCEL_TOKEN:-}" ]; then
  cat >&2 <<'MSG'
VERCEL_TOKEN is not set.

  1. Create a token:  https://vercel.com/account/tokens
     (scope: "Access Tokens" for the account, template: Full Access)
  2. Run:
       export VERCEL_TOKEN='<paste your token here>'
       ./deploy.sh
MSG
  exit 1
fi

cd "$(dirname "$0")/deploy"

echo "Deploying to Vercel..."
npx --yes vercel@latest deploy --prod --yes --token "$VERCEL_TOKEN" "$@"
