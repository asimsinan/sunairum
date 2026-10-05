#!/usr/bin/env bash
#
# Builds the three application images and pushes them to a registry so a host
# can deploy by pulling instead of building. Building on the target is the
# problem this solves: the worker image pulls ~900MB of torch and bakes 731MB of
# Docling weights, which competes for the same RAM the running stack needs.
#
# Run this from a workstation or CI, not from the deployment host.
#
#   IMAGE_PREFIX=ghcr.io/you/sunairum ./deploy/build-push.sh
#   IMAGE_PREFIX=registry.digitalocean.com/your-registry ./deploy/build-push.sh v1.2.0
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="${1:-${IMAGE_TAG:-latest}}"

if [[ -z "${IMAGE_PREFIX:-}" ]]; then
  printf 'IMAGE_PREFIX is required, for example:\n' >&2
  printf '  IMAGE_PREFIX=ghcr.io/you/sunairum %s\n' "$0" >&2
  exit 1
fi

# Droplets are amd64 while development machines are often arm64, and an image
# built for the wrong architecture fails at start with an exec format error.
PLATFORM="${PLATFORM:-linux/amd64}"

if ! docker buildx inspect sunairum-builder >/dev/null 2>&1; then
  docker buildx create --name sunairum-builder --use >/dev/null
else
  docker buildx use sunairum-builder
fi

build() {
  local name="$1" context="$2" dockerfile="$3"
  shift 3
  printf '\n==> %s/%s:%s (%s)\n' "$IMAGE_PREFIX" "$name" "$IMAGE_TAG" "$PLATFORM"
  docker buildx build \
    --platform "$PLATFORM" \
    --file "$context/$dockerfile" \
    --tag "$IMAGE_PREFIX/$name:$IMAGE_TAG" \
    --cache-from "type=registry,ref=$IMAGE_PREFIX/$name:buildcache" \
    --cache-to "type=registry,ref=$IMAGE_PREFIX/$name:buildcache,mode=max" \
    --push \
    "$@" \
    "$context"
}

# api and both Celery services share one image; compose only differs in command.
build api "$ROOT_DIR/servers/fastapi" Dockerfile
docker buildx imagetools create \
  --tag "$IMAGE_PREFIX/celery-generation:$IMAGE_TAG" \
  --tag "$IMAGE_PREFIX/celery-source-import:$IMAGE_TAG" \
  "$IMAGE_PREFIX/api:$IMAGE_TAG"

# No NEXT_PUBLIC_API_URL: the bundle calls its own origin through caddy, which is
# what keeps this image reusable across domains.
build web "$ROOT_DIR/servers/nextjs" Dockerfile.prod

printf '\nPushed:\n'
printf '  %s/api:%s\n'                   "$IMAGE_PREFIX" "$IMAGE_TAG"
printf '  %s/celery-generation:%s\n'     "$IMAGE_PREFIX" "$IMAGE_TAG"
printf '  %s/celery-source-import:%s\n'  "$IMAGE_PREFIX" "$IMAGE_TAG"
printf '  %s/web:%s\n'                   "$IMAGE_PREFIX" "$IMAGE_TAG"
printf '\nOn the host, set IMAGE_PREFIX=%s and IMAGE_TAG=%s in deploy/cloud.env, then run ./deploy/up.sh\n' \
  "$IMAGE_PREFIX" "$IMAGE_TAG"
