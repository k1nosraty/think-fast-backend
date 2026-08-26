#!/usr/bin/env sh
set -eu

umask 077
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:=5432}"
: "${BACKUP_DIR:?BACKUP_DIR is required}"

mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$BACKUP_DIR/think-fast-$stamp.dump"
pg_dump \
  --host "$POSTGRES_HOST" \
  --port "$POSTGRES_PORT" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --format custom \
  --compress 9 \
  --no-owner \
  --no-acl \
  --file "$target"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$target")" > "$(basename "$target").sha256")
printf '%s\n' "$target"
