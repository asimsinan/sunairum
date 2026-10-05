#!/usr/bin/env bash
#
# Prepares an existing Linux host to run the stack: installs Docker if missing,
# adds swap, and writes the two environment files if they do not exist yet.
#
# For a brand new DigitalOcean Droplet use deploy/cloud-init.yml instead, which
# does all of this at first boot.
#
#   sudo ./deploy/install.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'Run as root: sudo %s\n' "$0" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  printf '==> Installing Docker\n'
  curl -fsSL https://get.docker.com | sh
else
  printf '==> Docker already installed\n'
fi

# A Docling parse peaks near 2.3GB and LibreOffice spikes during rendered QA, so
# a burst can OOM-kill the worker on an 8GB host without swap to absorb it.
if [[ ! -f /swapfile ]] && ! swapon --show | grep -q .; then
  printf '==> Adding 4GB swap\n'
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
  printf '==> Swap already present\n'
fi

created=0
if [[ ! -f "$ROOT_DIR/deploy/cloud.env" ]]; then
  cp "$ROOT_DIR/deploy/cloud.env.example" "$ROOT_DIR/deploy/cloud.env"
  # A generated password beats leaving the placeholder in place, which would
  # otherwise become the database password on a public host.
  if command -v openssl >/dev/null 2>&1; then
    generated="$(openssl rand -base64 24 | tr -d '/+=')"
    sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$generated|" "$ROOT_DIR/deploy/cloud.env"
  fi
  chmod 600 "$ROOT_DIR/deploy/cloud.env"
  printf '==> Created deploy/cloud.env with a generated database password\n'
  created=1
fi

if [[ ! -f "$ROOT_DIR/deploy/fastapi.env" ]]; then
  cp "$ROOT_DIR/deploy/fastapi.env.example" "$ROOT_DIR/deploy/fastapi.env"
  chmod 600 "$ROOT_DIR/deploy/fastapi.env"
  printf '==> Created deploy/fastapi.env\n'
  created=1
fi

printf '\nNext steps:\n'
if [[ "$created" -eq 1 ]]; then
  printf '  1. Set SETTINGS_SECRET_KEY in deploy/fastapi.env\n'
  printf '  2. Set DOMAIN and IMAGE_PREFIX in deploy/cloud.env\n'
  printf '  3. ./deploy/up.sh          (or ./deploy/up.sh --build with no registry)\n'
  printf '  4. After login, set text/image/vision keys in the Settings UI\n'
else
  printf '  ./deploy/up.sh\n'
fi
