#!/usr/bin/env bash
# Keep desktop apps on GitHub, but out of the OCI working tree and (with
# blob:none fetch) out of what this host needs to download.
# Safe to re-run on every deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git config remote.origin.promisor true
git config remote.origin.partialclonefilter blob:none

git sparse-checkout init --no-cone
git sparse-checkout set \
  '/*' \
  '!/desktop/' \
  '!/desktop-offline/'

# Drop any previously checked-out desktop trees (no longer in the cone).
rm -rf desktop desktop-offline
