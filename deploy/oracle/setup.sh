#!/usr/bin/env bash
#
# Prepares an Oracle Cloud VM and starts the sunairum cloud stack.
#
# Run on the instance after SSH (recommended for private GitHub repos):
#
#   git clone https://github.com/asimsinan/sunairum.git && cd sunairum
#   sudo ./deploy/oracle/setup.sh
#
# Optional env:
#   SETTINGS_SECRET_KEY=...     written into deploy/fastapi.env if set
#   POSTGRES_PASSWORD=...       overrides generated DB password
#   DOMAIN=example.com          leave empty for http://PUBLIC_IP
#   IMAGE_PREFIX=ghcr.io/...    pull instead of building on the VM
#   CELERY_CONCURRENCY=1        default for Always Free Ampere
#   SKIP_BUILD=1                only install Docker/swap/firewall/env files
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCH="$(uname -m)"

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'Run as root: sudo %s\n' "$0" >&2
  exit 1
fi

printf '==> Architecture: %s\n' "$ARCH"
if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
  printf '    Ampere A1 (ARM). Images must be linux/arm64, or build on this host.\n'
else
  printf '    x86_64. Default build-push.sh images (linux/amd64) match this host.\n'
fi

bash "$ROOT_DIR/deploy/oracle/open-firewall.sh"
bash "$ROOT_DIR/deploy/install.sh"

CLOUD_ENV="$ROOT_DIR/deploy/cloud.env"
FASTAPI_ENV="$ROOT_DIR/deploy/fastapi.env"

# Always Free Ampere is 2 OCPU / 12 GB — one concurrent Docling parse is safer.
if grep -qE '^CELERY_CONCURRENCY=' "$CLOUD_ENV"; then
  sed -i 's|^CELERY_CONCURRENCY=.*|CELERY_CONCURRENCY='"${CELERY_CONCURRENCY:-1}"'|' "$CLOUD_ENV"
else
  printf 'CELERY_CONCURRENCY=%s\n' "${CELERY_CONCURRENCY:-1}" >>"$CLOUD_ENV"
fi

if [[ -n "${DOMAIN:-}" ]]; then
  sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" "$CLOUD_ENV"
fi

if [[ -n "${POSTGRES_PASSWORD:-}" ]]; then
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" "$CLOUD_ENV"
fi

if [[ -n "${IMAGE_PREFIX:-}" ]]; then
  sed -i "s|^IMAGE_PREFIX=.*|IMAGE_PREFIX=$IMAGE_PREFIX|" "$CLOUD_ENV"
fi

if [[ -n "${SETTINGS_SECRET_KEY:-}" ]]; then
  if grep -qE '^SETTINGS_SECRET_KEY=' "$FASTAPI_ENV"; then
    sed -i "s|^SETTINGS_SECRET_KEY=.*|SETTINGS_SECRET_KEY=$SETTINGS_SECRET_KEY|" "$FASTAPI_ENV"
  else
    printf 'SETTINGS_SECRET_KEY=%s\n' "$SETTINGS_SECRET_KEY" >>"$FASTAPI_ENV"
  fi
fi

printf '\nNote: configure text/image/vision models in the Settings UI after login (Google/Gemini unsupported).\n'

if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
  printf '\nSKIP_BUILD=1 — env and firewall ready. Start later with:\n'
  printf '  cd %s && ./deploy/up.sh --build\n' "$ROOT_DIR"
  exit 0
fi

cd "$ROOT_DIR"
if grep -qE '^IMAGE_PREFIX=(ghcr\.io/your-org/sunairum|CHANGE_ME)' "$CLOUD_ENV" \
  || grep -qE '^IMAGE_PREFIX=$' "$CLOUD_ENV"; then
  printf '==> No usable IMAGE_PREFIX — building on the host (long first run)\n'
  ./deploy/up.sh --build
else
  printf '==> Pulling images from IMAGE_PREFIX in cloud.env\n'
  ./deploy/up.sh
fi

PUBLIC_IP="$(curl -fsS --max-time 5 ifconfig.me 2>/dev/null || true)"

printf '\nStack starting.\n'
if [[ -n "$PUBLIC_IP" ]]; then
  printf 'Open: http://%s\n' "$PUBLIC_IP"
else
  printf 'Open: http://<instance-public-ip>  (see OCI console)\n'
fi
printf 'Status: ./deploy/status.sh\n'
