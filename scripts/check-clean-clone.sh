#!/usr/bin/env bash
# Clones the repo into a temp dir, starts the stack with default settings,
# waits for /api/ready, runs the e2e smoke and newman, then cleans up.
#
# Usage: scripts/check-clean-clone.sh [repo-url-or-path] [ref]
#   defaults: this repository, current branch
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${1:-$ROOT}"
REF="${2:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)}"
PROJECT="cleanclone$$"
PORT="${CLEAN_CLONE_PORT:-18080}"
WORKDIR="$(mktemp -d)"

cleanup() {
  echo "==> Cleaning up"
  (cd "$WORKDIR/repo" 2>/dev/null && docker compose -p "$PROJECT" down -v --remove-orphans >/dev/null 2>&1) || true
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

echo "==> Cloning $REPO ($REF) into $WORKDIR/repo"
git clone --quiet --branch "$REF" "$REPO" "$WORKDIR/repo"
cd "$WORKDIR/repo"

echo "==> Starting the stack with .env.example as is"
cp .env.example .env
WEB_PORT="$PORT" CSRF_TRUSTED_ORIGINS="http://localhost:$PORT" \
  docker compose -p "$PROJECT" up -d --build --wait

echo "==> Waiting for /api/ready"
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:$PORT/api/ready" >/dev/null; then break; fi
  sleep 2
done
curl -fsS "http://localhost:$PORT/api/ready"
echo

NETWORK="${PROJECT}_default"
PW_VERSION="$(sed -n 's/.*"@playwright\/test": *"\([^"]*\)".*/\1/p' e2e/package.json)"

# Git Bash on Windows: keep docker paths as is and pass a Windows host path for mounts.
export MSYS_NO_PATHCONV=1
HOST_PWD="$(pwd -W 2>/dev/null || pwd)"

echo "==> E2E smoke (Playwright $PW_VERSION)"
docker run --rm --network "$NETWORK" -e BASE_URL=http://web -e CI=1 \
  -v "$HOST_PWD/e2e:/src:ro" "mcr.microsoft.com/playwright:v${PW_VERSION}-noble" \
  sh -c "cp -r /src /e2e && cd /e2e && npm ci --no-audit --no-fund && npx playwright test"

echo "==> Newman"
docker run --rm --network "$NETWORK" -v "$HOST_PWD/postman:/etc/newman:ro" postman/newman:6-alpine \
  run collection.json --env-var baseUrl=http://web

echo "==> Clean clone check passed"
