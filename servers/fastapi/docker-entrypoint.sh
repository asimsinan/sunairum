#!/bin/sh
# Drop root before uvicorn/celery. Celery 5+ warns (and Celery 6 may refuse)
# when the worker runs with euid=0; named volumes also start root-owned, so
# fix /app/storage while we still can, then hand off to `app`.
set -eu

mkdir -p /app/storage

if [ "$(id -u)" = "0" ]; then
  chown app:app /app/storage || true
  if ! gosu app test -w /app/storage; then
    chown -R app:app /app/storage
  fi
  exec gosu app "$@"
fi

exec "$@"
