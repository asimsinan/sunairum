#!/usr/bin/env bash
#
# Starts or updates the cloud stack.
#
# Pulls prebuilt images by default. Building here instead would fetch ~900MB of
# torch and bake 731MB of Docling weights on the host, competing for the RAM the
# running stack needs, so `--build` is opt-in for hosts with no registry.
#
#   ./deploy/up.sh                     # pull and start
#   ./deploy/up.sh --build             # build locally, then start
#   ./deploy/up.sh /path/to/cloud.env  # use a different environment file
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.cloud.yml"

BUILD=0
CLOUD_ENV=""
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) CLOUD_ENV="$arg" ;;
  esac
done

CLOUD_ENV="${CLOUD_ENV:-$ROOT_DIR/deploy/cloud.env}"
FASTAPI_ENV="${FASTAPI_ENV_FILE:-$ROOT_DIR/deploy/fastapi.env}"

if [[ ! -f "$CLOUD_ENV" ]]; then
  printf 'Missing cloud environment file: %s\n' "$CLOUD_ENV" >&2
  printf 'Create it with: cp deploy/cloud.env.example deploy/cloud.env\n' >&2
  exit 1
fi

if [[ ! -f "$FASTAPI_ENV" ]]; then
  printf 'Missing FastAPI environment file: %s\n' "$FASTAPI_ENV" >&2
  printf 'Create it with: cp deploy/fastapi.env.example deploy/fastapi.env\n' >&2
  exit 1
fi

compose() {
  docker compose --env-file "$CLOUD_ENV" -f "$COMPOSE_FILE" "$@"
}

if [[ "$BUILD" -eq 1 ]]; then
  compose build
else
  # Postgres, Redis and Caddy always come from upstream; the application images
  # come from IMAGE_PREFIX. A pull failure here is usually an unset IMAGE_PREFIX
  # or a registry the host has not logged in to, so say so rather than falling
  # back to a surprise build.
  if ! compose pull; then
    printf '\nPull failed. Check IMAGE_PREFIX and IMAGE_TAG in %s, and that this host\n' "$CLOUD_ENV" >&2
    printf 'is logged in to the registry (docker login). To build here instead:\n' >&2
    printf '  %s --build\n' "$0" >&2
    exit 1
  fi
fi

compose up -d --remove-orphans
