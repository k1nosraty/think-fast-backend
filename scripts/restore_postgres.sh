#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:=5432}"
: "${RESTORE_FILE:?RESTORE_FILE is required}"
: "${RESTORE_CONFIRM_DATABASE:?RESTORE_CONFIRM_DATABASE is required}"

if [ "$RESTORE_CONFIRM_DATABASE" != "$POSTGRES_DB" ]; then
  printf '%s\n' "RESTORE_CONFIRM_DATABASE must exactly match POSTGRES_DB" >&2
  exit 2
fi
if [ ! -f "$RESTORE_FILE" ] || [ ! -f "$RESTORE_FILE.sha256" ]; then
  printf '%s\n' "Backup and matching .sha256 file are required" >&2
  exit 2
fi
(cd "$(dirname "$RESTORE_FILE")" && sha256sum --check "$(basename "$RESTORE_FILE").sha256")
pg_restore \
  --host "$POSTGRES_HOST" \
  --port "$POSTGRES_PORT" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  --exit-on-error \
  "$RESTORE_FILE"
