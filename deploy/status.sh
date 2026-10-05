#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLOUD_ENV="${1:-$ROOT_DIR/deploy/cloud.env}"

exec docker compose \
  --env-file "$CLOUD_ENV" \
  -f "$ROOT_DIR/docker-compose.cloud.yml" \
  ps
