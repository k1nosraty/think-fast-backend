#!/usr/bin/env bash
set -uo pipefail

# One-command T8 validation runner for Ubuntu 22.04/24.04.
# It never restores over the source database. A timestamped, isolated database
# is created for the restore drill and removed during cleanup.

export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/usr/lib/postgresql/17/bin:$PATH"

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
ARTIFACT_DIR=${ARTIFACT_DIR:-"$ROOT_DIR/artifacts/t8-validation-$RUN_ID"}
REPORT_FILE="$ARTIFACT_DIR/report.md"
LOG_DIR="$ARTIFACT_DIR/logs"
BACKUP_DIR="$ARTIFACT_DIR/backup"
FIXTURE_FILE="$ARTIFACT_DIR/resilience-fixture.json"
LOCAL_BASE_URL=${LOCAL_BASE_URL:-http://127.0.0.1:8000}
BASE_URL=${BASE_URL:-$LOCAL_BASE_URL}
INSTALL_PREREQUISITES=${INSTALL_PREREQUISITES:-true}
RUN_LOAD_TESTS=${RUN_LOAD_TESTS:-true}
RUN_IMAGE_SCAN=${RUN_IMAGE_SCAN:-true}
RUN_RESILIENCE_DRILLS=${RUN_RESILIENCE_DRILLS:-true}
KEEP_STACK=${KEEP_STACK:-false}
ALLOW_REMOTE_DB_DRILL=${ALLOW_REMOTE_DB_DRILL:-false}
RETRY_GATES=${RETRY_GATES:-}
REQUIRED_NOFILE=${REQUIRED_NOFILE:-65536}
RESTORE_DB="think_fast_restore_validation_${RUN_ID//[^0-9]/}"
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-"think-fast-t8-${RUN_ID//[^0-9]/}"}
IMAGE_TAG=${IMAGE_TAG:-"think-fast-backend:t8-validation-$RUN_ID"}
REUSE_IMAGE_TAG=${REUSE_IMAGE_TAG:-}
LOAD_FIXTURE_START_BASE=${LOAD_FIXTURE_START_BASE:-$(( $(date -u +%s) % 900000000 ))}
APP_PID=""
SOURCE_DB=${POSTGRES_DB:-think_fast}
FAILED=0
REPORT_WRITTEN=0
LOCAL_APP_READY=0

mkdir -p "$LOG_DIR" "$BACKUP_DIR"
chmod 700 "$ARTIFACT_DIR" "$LOG_DIR" "$BACKUP_DIR"

declare -a RESULTS=()

gate_enabled() {
  local gate=$1
  [[ -z "$RETRY_GATES" || ",$RETRY_GATES," == *",$gate,"* ]]
}

configure_file_limit() {
  if ! gate_enabled sockets_2000; then
    record "file descriptor limit" SKIP "sockets_2000 is not selected"
    return
  fi

  local hard_limit effective_limit
  hard_limit=$(ulimit -Hn)
  if [[ "$hard_limit" != "unlimited" && "$hard_limit" -lt "$REQUIRED_NOFILE" ]]; then
    record "file descriptor limit" FAIL \
      "hard nofile=$hard_limit is below required=$REQUIRED_NOFILE; raise LimitNOFILE and retry"
    return
  fi
  if ! ulimit -Sn "$REQUIRED_NOFILE"; then
    record "file descriptor limit" FAIL "could not set soft nofile=$REQUIRED_NOFILE"
    return
  fi
  effective_limit=$(ulimit -Sn)
  record "file descriptor limit" PASS \
    "soft=$effective_limit hard=$hard_limit; inherited by Daphne and k6"
}

record() {
  local name=$1 status=$2 detail=$3
  RESULTS+=("$name|$status|$detail")
  printf '%-34s %-5s %s\n' "$name" "$status" "$detail"
  [[ "$status" != "FAIL" ]] || FAILED=1
}

run_gate() {
  local name=$1 log_name=$2
  shift 2
  local started ended rc
  started=$(date +%s)
  set +e
  "$@" >"$LOG_DIR/$log_name.log" 2>&1
  rc=$?
  set -e
  ended=$(date +%s)
  if [[ $rc -eq 0 ]]; then
    record "$name" PASS "$((ended - started))s; logs/$log_name.log"
  else
    record "$name" FAIL "exit=$rc; $((ended - started))s; logs/$log_name.log"
  fi
  return 0
}

as_root() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    printf 'sudo is required to install system prerequisites\n' >&2
    return 1
  fi
}

install_prerequisites() {
  if [[ "$INSTALL_PREREQUISITES" != "true" ]]; then
    record "prerequisite installation" SKIP "INSTALL_PREREQUISITES=false"
    return
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    record "prerequisite installation" FAIL "only Ubuntu/Debian apt is supported"
    return
  fi

  run_gate "apt prerequisites" install-apt as_root env DEBIAN_FRONTEND=noninteractive \
    apt-get update
  run_gate "system packages" install-packages as_root env DEBIAN_FRONTEND=noninteractive \
    apt-get install -y ca-certificates curl gnupg postgresql-common docker.io docker-compose-v2

  if [[ ! -x /usr/lib/postgresql/17/bin/pg_dump ]]; then
    run_gate "PostgreSQL repository" install-postgresql-repository bash -c \
      'sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y'
    run_gate "PostgreSQL 17 client" install-postgresql-client as_root env \
      DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-client-17
  else
    record "PostgreSQL 17 client" PASS "already installed"
  fi
  export PATH="/usr/lib/postgresql/17/bin:$PATH"

  if ! command -v uv >/dev/null 2>&1; then
    run_gate "uv installation" install-uv bash -c \
      'curl -LsSf https://astral.sh/uv/0.11.33/install.sh | sh'
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  else
    record "uv installation" PASS "already installed: $(uv --version 2>/dev/null || true)"
  fi

  if ! command -v k6 >/dev/null 2>&1; then
    run_gate "k6 repository" install-k6-repository bash -c \
      'curl -fsSL https://dl.k6.io/key.gpg | sudo gpg --dearmor --yes -o /usr/share/keyrings/k6-archive-keyring.gpg && echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list >/dev/null && sudo apt-get update'
    run_gate "k6 installation" install-k6 as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y k6
  else
    record "k6 installation" PASS "already installed: $(k6 version 2>/dev/null | head -n 1)"
  fi

  if [[ "$RUN_IMAGE_SCAN" == "true" ]] && ! command -v trivy >/dev/null 2>&1; then
    run_gate "Trivy installation" install-trivy bash -c \
      'curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sudo sh -s -- -b /usr/local/bin v0.69.3'
  elif command -v trivy >/dev/null 2>&1; then
    record "Trivy installation" PASS "already installed: $(trivy --version 2>/dev/null | head -n 1)"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    as_root systemctl start docker >"$LOG_DIR/docker-start.log" 2>&1 || true
  fi
  if ! docker info >/dev/null 2>&1; then
    record "Docker daemon" FAIL "Docker is unavailable; add this user to docker group or run with sudo"
  else
    record "Docker daemon" PASS "available"
  fi
}

cleanup() {
  if [[ -n "$APP_PID" ]]; then
    kill "$APP_PID" >/dev/null 2>&1 || true
    wait "$APP_PID" >/dev/null 2>&1 || true
  fi
  if [[ "$BASE_URL" == "$LOCAL_BASE_URL" && "$KEEP_STACK" != "true" ]] && command -v docker >/dev/null 2>&1; then
    docker compose -p "$COMPOSE_PROJECT_NAME" -f "$ROOT_DIR/compose.yaml" down --volumes >/dev/null 2>&1 || true
  fi
  if command -v psql >/dev/null 2>&1 && [[ -n "${POSTGRES_HOST:-}" ]]; then
    PGPASSWORD=${POSTGRES_PASSWORD:-} psql -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" \
      -U "${POSTGRES_USER:-think_fast}" -d postgres -v ON_ERROR_STOP=1 \
      -c "DROP DATABASE IF EXISTS \"$RESTORE_DB\" WITH (FORCE);" >/dev/null 2>&1 || true
  fi
  if [[ $REPORT_WRITTEN -eq 0 && -d "$ARTIFACT_DIR" ]]; then
    write_report || true
  fi
}
trap cleanup EXIT INT TERM

wait_for_url() {
  local url=$1 attempts=${2:-60}
  for ((i=1; i<=attempts; i++)); do
    curl --fail --silent "$url" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

start_local_validation() {
  if [[ "$BASE_URL" != "$LOCAL_BASE_URL" ]]; then
    record "local validation stack" SKIP "using external BASE_URL=$BASE_URL"
    return
  fi

  export POSTGRES_DB=${POSTGRES_DB:-think_fast}
  export POSTGRES_USER=${POSTGRES_USER:-think_fast}
  export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-think_fast_local}
  export POSTGRES_HOST=${POSTGRES_HOST:-127.0.0.1}
  export POSTGRES_PORT=${POSTGRES_PORT:-5432}
  export REDIS_URL=${REDIS_URL:-redis://127.0.0.1:6379/0}
  export DJANGO_SETTINGS_MODULE=config.settings.local
  # Capacity measurement runs with DEBUG off so Django does not retain every SQL
  # query on the connection, which would distort latency and memory over a long run.
  export DJANGO_DEBUG=${DJANGO_DEBUG:-false}
  # Bound the PostgreSQL connection pool explicitly so the exhaustion path that
  # produced the T8 Guess-load failures ("too many clients already") cannot recur.
  export POSTGRES_POOL_ENABLED=${POSTGRES_POOL_ENABLED:-true}
  export GAME_SECRET_ENCRYPTION_KEY=${GAME_SECRET_ENCRYPTION_KEY:-MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=}
  export LOAD_FIXTURES_ENABLED=true
  export PGPASSWORD=$POSTGRES_PASSWORD

  local stale_project port
  declare -A stale_projects=()
  for port in 5432 6379; do
    while IFS= read -r stale_project; do
      [[ -n "$stale_project" ]] && stale_projects["$stale_project"]=1
    done < <(docker ps --filter "publish=$port" \
      --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null)
  done
  for stale_project in "${!stale_projects[@]}"; do
    if [[ "$stale_project" =~ ^think-fast-t8-[0-9]+$ ]]; then
      run_gate "stale validation cleanup" "cleanup-$stale_project" docker compose \
        -p "$stale_project" -f "$ROOT_DIR/compose.yaml" down --volumes
    else
      record "dependency port ownership" FAIL \
        "ports 5432/6379 are owned by non-runner compose project=$stale_project"
    fi
  done
  if [[ $FAILED -ne 0 ]]; then
    return
  fi

  if ! python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 8000)); s.close()' \
    >"$LOG_DIR/port-8000-preflight.log" 2>&1; then
    record "local port preflight" FAIL "127.0.0.1:8000 is already in use; refusing to test an unknown process"
    return
  fi
  record "local port preflight" PASS "127.0.0.1:8000 is free"

  run_gate "dependency containers" compose-up docker compose -p "$COMPOSE_PROJECT_NAME" \
    -f "$ROOT_DIR/compose.yaml" up -d --wait
  if [[ $FAILED -ne 0 ]]; then
    return
  fi
  run_gate "locked dependency sync" uv-sync uv sync --locked --dev
  if [[ $FAILED -ne 0 ]]; then
    return
  fi
  run_gate "database migrations" migrate uv run python manage.py migrate --noinput
  if [[ $FAILED -ne 0 ]]; then
    return
  fi

  "$ROOT_DIR/.venv/bin/daphne" --access-log /dev/null -b 127.0.0.1 -p 8000 \
    config.asgi:application >"$LOG_DIR/daphne.log" 2>&1 &
  APP_PID=$!
  if kill -0 "$APP_PID" >/dev/null 2>&1 && wait_for_url "$LOCAL_BASE_URL/health/live/" 60; then
    LOCAL_APP_READY=1
    record "local application" PASS "pid=$APP_PID"
  else
    record "local application" FAIL "did not become live; logs/daphne.log"
  fi
}

restart_local_app() {
  [[ -n "$APP_PID" ]] && kill "$APP_PID" >/dev/null 2>&1 || true
  [[ -n "$APP_PID" ]] && wait "$APP_PID" >/dev/null 2>&1 || true
  "$ROOT_DIR/.venv/bin/daphne" --access-log /dev/null -b 127.0.0.1 -p 8000 \
    config.asgi:application >"$LOG_DIR/daphne-restarted.log" 2>&1 &
  APP_PID=$!
  wait_for_url "$LOCAL_BASE_URL/health/live/" 60
}

run_image_gate() {
  if ! gate_enabled image_scan; then
    record "production image and scan" SKIP "not selected by RETRY_GATES"
    return
  fi
  if [[ "$RUN_IMAGE_SCAN" != "true" ]]; then
    record "production image and scan" SKIP "RUN_IMAGE_SCAN=false"
    return
  fi
  if [[ -n "$REUSE_IMAGE_TAG" ]]; then
    if docker image inspect "$REUSE_IMAGE_TAG" >/dev/null 2>&1; then
      IMAGE_TAG=$REUSE_IMAGE_TAG
      record "production image build" SKIP "reusing existing image=$IMAGE_TAG"
    else
      record "production image build" FAIL "REUSE_IMAGE_TAG not found: $REUSE_IMAGE_TAG"
      return
    fi
  else
    run_gate "production image build" image-build docker build --tag "$IMAGE_TAG" "$ROOT_DIR"
  fi
  if ! command -v trivy >/dev/null 2>&1; then
    record "production image scan" FAIL "trivy is unavailable"
  elif docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
    local db_ready=0 repository
    for repository in \
      public.ecr.aws/aquasecurity/trivy-db:2 \
      ghcr.io/aquasecurity/trivy-db:2; do
      if env TRIVY_DB_REPOSITORY="$repository" trivy image --download-db-only \
        >>"$LOG_DIR/image-db.log" 2>&1; then
        db_ready=1
        break
      fi
    done
    if [[ $db_ready -eq 1 ]]; then
      run_gate "production image inventory" image-inventory docker run --rm \
        --entrypoint /app/.venv/bin/python "$IMAGE_TAG" -c \
        'import sys; from importlib.metadata import distributions; p={d.metadata["Name"].lower(): d.version for d in distributions()}; print("executable={} prefix={} msgpack={}".format(sys.executable, sys.prefix, p.get("msgpack"))); assert p.get("msgpack") == "1.2.1", p; assert not ({"setuptools", "bandit", "pip-audit", "pytest", "mypy", "ruff"} & p.keys()), sorted(p); print("runtime inventory clean; dev/build tools absent")'
      run_gate "production image scan" image-scan trivy image --skip-db-update \
        --skip-version-check --scanners vuln --detection-priority precise \
        --skip-dirs "**/sboms" --skip-files "**/sboms/**" \
        --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "$IMAGE_TAG"
    else
      record "production image scan" FAIL "vulnerability DB download failed; logs/image-db.log"
    fi
  else
    record "production image scan" FAIL "image build did not produce $IMAGE_TAG"
  fi
}

run_restore_drill() {
  if ! gate_enabled backup_restore; then
    record "backup/restore drill" SKIP "not selected by RETRY_GATES"
    return
  fi
  if [[ "$BASE_URL" != "$LOCAL_BASE_URL" && "$ALLOW_REMOTE_DB_DRILL" != "true" ]]; then
    record "backup/restore drill" SKIP "set ALLOW_REMOTE_DB_DRILL=true after confirming permission to create a temporary database"
    return
  fi
  if [[ "$BASE_URL" != "$LOCAL_BASE_URL" && -z "${POSTGRES_HOST:-}" ]]; then
    record "backup/restore drill" SKIP "external run requires PostgreSQL environment variables"
    return
  fi
  if [[ -z "${POSTGRES_DB:-}" || -z "${POSTGRES_USER:-}" || -z "${POSTGRES_HOST:-}" ]]; then
    record "backup/restore drill" FAIL "POSTGRES_DB, POSTGRES_USER and POSTGRES_HOST are required"
    return
  fi
  POSTGRES_PORT=${POSTGRES_PORT:-5432}
  local backup_file start end source_count restored_count
  export PGPASSWORD=${POSTGRES_PASSWORD:-}
  set +e
  backup_file=$(BACKUP_DIR="$BACKUP_DIR" "$ROOT_DIR/scripts/backup_postgres.sh" \
    2>"$LOG_DIR/backup.log")
  local backup_rc=$?
  set -e
  if [[ $backup_rc -ne 0 || ! -f "$backup_file" ]]; then
    record "backup/restore drill" FAIL "backup failed; logs/backup.log"
    return
  fi

  start=$(date +%s)
  if ! psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres \
    -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$RESTORE_DB\";" \
    >"$LOG_DIR/restore-create-db.log" 2>&1; then
    record "backup/restore drill" FAIL "could not create isolated restore database"
    return
  fi
  set +e
  POSTGRES_DB="$RESTORE_DB" RESTORE_CONFIRM_DATABASE="$RESTORE_DB" RESTORE_FILE="$backup_file" \
    "$ROOT_DIR/scripts/restore_postgres.sh" >"$LOG_DIR/restore.log" 2>&1
  local restore_rc=$?
  set -e
  end=$(date +%s)
  if [[ $restore_rc -ne 0 ]]; then
    record "backup/restore drill" FAIL "restore failed; logs/restore.log"
    return
  fi
  source_count=$(psql -At -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    -d "$SOURCE_DB" -c "SELECT count(*) FROM django_migrations;" 2>/dev/null || echo error)
  restored_count=$(psql -At -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    -d "$RESTORE_DB" -c "SELECT count(*) FROM django_migrations;" 2>/dev/null || echo error)
  if [[ "$source_count" == "$restored_count" && "$source_count" != "error" ]]; then
    record "backup/restore drill" PASS "RTO=$((end - start))s; migration_rows=$restored_count"
  else
    record "backup/restore drill" FAIL "row verification mismatch: source=$source_count restored=$restored_count"
  fi
}

run_local_resilience_drills() {
  if ! gate_enabled redis_recovery && ! gate_enabled app_restart; then
    record "Redis/restart drills" SKIP "not selected by RETRY_GATES"
    return
  fi
  if [[ "$RUN_RESILIENCE_DRILLS" != "true" ]]; then
    record "Redis/restart drills" SKIP "RUN_RESILIENCE_DRILLS=false"
    return
  fi
  if [[ "$BASE_URL" != "$LOCAL_BASE_URL" ]]; then
    record "Redis failure/recovery" SKIP "remote infrastructure control is intentionally not assumed"
    record "application restart/recovery" SKIP "remote deployment control is intentionally not assumed"
    return
  fi
  if [[ $LOCAL_APP_READY -ne 1 ]]; then
    record "Redis failure/recovery" SKIP "the runner-owned local application is unavailable"
    record "application restart/recovery" SKIP "the runner-owned local application is unavailable"
    return
  fi
  if [[ ! -f "$FIXTURE_FILE" ]]; then
    run_gate "resilience fixture preparation" resilience-fixture uv run python manage.py \
      prepare_load_fixtures --count 1 --start-index "$((LOAD_FIXTURE_START_BASE + 9000))" \
      --output "$FIXTURE_FILE"
  fi
  if [[ ! -f "$FIXTURE_FILE" ]]; then
    record "Redis failure/recovery" FAIL "fixture preparation failed"
    record "application restart/recovery" FAIL "fixture preparation failed"
    return
  fi
  chmod 600 "$FIXTURE_FILE"

  local match_id token http_code
  match_id=$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1]))[0]["match_id"])' "$FIXTURE_FILE")
  token=$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1]))[0]["token"])' "$FIXTURE_FILE")
  docker compose -p "$COMPOSE_PROJECT_NAME" -f "$ROOT_DIR/compose.yaml" stop redis \
    >"$LOG_DIR/redis-stop.log" 2>&1 || true
  http_code=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    -H "Authorization: Bearer $token" "$BASE_URL/api/v1/matches/$match_id/snapshot/" || true)
  docker compose -p "$COMPOSE_PROJECT_NAME" -f "$ROOT_DIR/compose.yaml" start redis \
    >"$LOG_DIR/redis-start.log" 2>&1 || true
  if wait_for_url "$BASE_URL/health/ready/" 60 && [[ "$http_code" == "200" ]]; then
    run_gate "outbox recovery" publish-outbox uv run python manage.py publish_outbox --limit 1000
    record "Redis failure/recovery" PASS "durable snapshot remained available; readiness and outbox recovered"
  else
    record "Redis failure/recovery" FAIL "snapshot_status=$http_code or readiness did not recover"
  fi

  if restart_local_app && [[ $(curl --silent --output /dev/null --write-out '%{http_code}' \
    -H "Authorization: Bearer $token" "$BASE_URL/api/v1/matches/$match_id/snapshot/" || true) == "200" ]]; then
    record "application restart/recovery" PASS "authenticated snapshot recovered after ASGI restart"
  else
    record "application restart/recovery" FAIL "application or snapshot did not recover; logs/daphne-restarted.log"
  fi
  if command -v shred >/dev/null 2>&1; then shred --remove "$FIXTURE_FILE"; else rm -f -- "$FIXTURE_FILE"; fi
}

run_load_profiles() {
  if [[ "$RUN_LOAD_TESTS" != "true" ]]; then
    record "capacity profiles" SKIP "RUN_LOAD_TESTS=false"
    return
  fi
  if [[ "$BASE_URL" != "$LOCAL_BASE_URL" && -z "${LOAD_FIXTURE_FILE:-}" ]]; then
    record "capacity profiles" SKIP "external staging requires LOAD_FIXTURE_FILE generated on that environment"
    return
  fi
  if [[ "$BASE_URL" == "$LOCAL_BASE_URL" && $LOCAL_APP_READY -ne 1 ]]; then
    record "capacity profiles" SKIP "the runner-owned local application is unavailable"
    return
  fi
  for profile in guess_sustained guess_burst sockets_2000 reconnect_1000; do
    if ! gate_enabled "$profile"; then
      record "k6 $profile" SKIP "not selected by RETRY_GATES"
      continue
    fi
    local profile_fixture="$ARTIFACT_DIR/load-fixtures-$profile.json"
    local start_index=$LOAD_FIXTURE_START_BASE
    if [[ "$BASE_URL" == "$LOCAL_BASE_URL" ]]; then
      local fixture_count=${LOAD_FIXTURE_COUNT:-3000}
      [[ "$profile" == "guess_burst" ]] && start_index=$((LOAD_FIXTURE_START_BASE + 3000))
      [[ "$profile" == "sockets_2000" ]] && { fixture_count=2000; start_index=$((LOAD_FIXTURE_START_BASE + 6000)); }
      [[ "$profile" == "reconnect_1000" ]] && { fixture_count=1000; start_index=$((LOAD_FIXTURE_START_BASE + 8000)); }
      run_gate "fixtures $profile" "fixtures-$profile" uv run python manage.py \
        prepare_load_fixtures --count "$fixture_count" --start-index "$start_index" \
        --output "$profile_fixture"
    else
      profile_fixture=$LOAD_FIXTURE_FILE
    fi
    if [[ ! -f "$profile_fixture" ]]; then
      record "k6 $profile" FAIL "fixture file missing"
      continue
    fi
    chmod 600 "$profile_fixture"
    local fd_sampler_pid=""
    if [[ "$profile" == "sockets_2000" && -n "$APP_PID" ]]; then
      (
        while kill -0 "$APP_PID" >/dev/null 2>&1; do
          printf '%s app_open_fds=%s\n' "$(date -u +%FT%TZ)" \
            "$(find "/proc/$APP_PID/fd" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)"
          sleep 1
        done
      ) >"$LOG_DIR/app-fd-sockets_2000.log" 2>&1 &
      fd_sampler_pid=$!
    fi
    # Record the live PostgreSQL backend count for the application role while the
    # profile runs. This is the evidence that the psycopg pool bounds checkouts:
    # holding 2,000 WebSockets must not drive 2,000 backends. Only meaningful for
    # the runner-owned local stack, where PG* point at the compose Postgres.
    local db_sampler_pid=""
    if [[ "$BASE_URL" == "$LOCAL_BASE_URL" ]]; then
      (
        while kill -0 "$APP_PID" >/dev/null 2>&1; do
          printf '%s backends=%s\n' "$(date -u +%FT%TZ)" \
            "$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
              -d "$POSTGRES_DB" -tAc \
              "select count(*) from pg_stat_activity where usename='$POSTGRES_USER'" \
              2>/dev/null | tr -d '[:space:]')"
          sleep 1
        done
      ) >"$LOG_DIR/db-connections-$profile.log" 2>&1 &
      db_sampler_pid=$!
    fi
    run_gate "k6 $profile" "k6-$profile" env PROFILE="$profile" BASE_URL="$BASE_URL" \
      LOAD_FIXTURE_FILE="$profile_fixture" k6 run --summary-export "$ARTIFACT_DIR/k6-$profile-summary.json" \
      "$ROOT_DIR/tests/load/k6_beta.js"
    if [[ -n "$fd_sampler_pid" ]]; then
      kill "$fd_sampler_pid" >/dev/null 2>&1 || true
      wait "$fd_sampler_pid" >/dev/null 2>&1 || true
    fi
    if [[ -n "$db_sampler_pid" ]]; then
      kill "$db_sampler_pid" >/dev/null 2>&1 || true
      wait "$db_sampler_pid" >/dev/null 2>&1 || true
    fi
    if [[ "$BASE_URL" == "$LOCAL_BASE_URL" ]]; then
      if command -v shred >/dev/null 2>&1; then shred --remove "$profile_fixture"; else rm -f -- "$profile_fixture"; fi
    fi
  done
}

write_report() {
  local scope="external staging"
  [[ "$BASE_URL" != "$LOCAL_BASE_URL" ]] || scope="single-host local validation (not production capacity evidence)"
  {
    printf '# Think Fast T8 validation report\n\n'
    printf -- '- Run ID: `%s`\n' "$RUN_ID"
    printf -- '- Generated (UTC): `%s`\n' "$(date -u +%FT%TZ)"
    printf -- '- Git commit: `%s`\n' "$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo unavailable)"
    printf -- '- Base URL: `%s`\n' "$BASE_URL"
    printf -- '- Evidence scope: **%s**\n' "$scope"
    printf -- '- Host: `%s`\n\n' "$(uname -a)"
    printf -- '- Runner options: `load=%s image_scan=%s resilience=%s remote_db_drill=%s`\n\n' \
      "$RUN_LOAD_TESTS" "$RUN_IMAGE_SCAN" "$RUN_RESILIENCE_DRILLS" "$ALLOW_REMOTE_DB_DRILL"
    if [[ "$BASE_URL" == "$LOCAL_BASE_URL" ]]; then
      printf -- '- Capacity config: `debug=%s pool_enabled=%s pool_min=%s pool_max=%s pool_timeout=%s`\n\n' \
        "${DJANGO_DEBUG:-unset}" "${POSTGRES_POOL_ENABLED:-unset}" \
        "${POSTGRES_POOL_MIN:-4}" "${POSTGRES_POOL_MAX:-32}" "${POSTGRES_POOL_TIMEOUT:-10}"
    fi
    printf -- '- Retry gates: `%s`\n\n' "${RETRY_GATES:-all}"
    printf '| Gate | Status | Evidence |\n| --- | --- | --- |\n'
    local row name status detail
    for row in "${RESULTS[@]}"; do
      IFS='|' read -r name status detail <<<"$row"
      printf '| %s | **%s** | %s |\n' "$name" "$status" "$detail"
    done
    printf '\n## Interpretation\n\n'
    if [[ $FAILED -eq 0 ]]; then
      printf 'All executed gates passed. '
    else
      printf 'One or more executed gates failed. '
    fi
    if [[ "$BASE_URL" == "$LOCAL_BASE_URL" ]]; then
      printf 'This single-host run validates the harness and provides a baseline; it does not by itself close the production staging capacity gate.\n'
    else
      printf 'Attach infrastructure graphs and verify the agreed staging topology before approving the T8 exit gate.\n'
    fi
    printf '\nFull command output is stored under `logs/`; k6 machine summaries are adjacent to this report. Secrets and fixture contents must not be shared.\n'
  } >"$REPORT_FILE"
  chmod 600 "$REPORT_FILE"
  REPORT_WRITTEN=1
  printf '\nReport: %s\n' "$REPORT_FILE"
}

main() {
  cd "$ROOT_DIR"
  set -e
  if [[ -f "$ROOT_DIR/config/settings.py" ]]; then
    record "clean extraction" FAIL "obsolete config/settings.py found; extract this release into a new empty directory"
    write_report
    return 1
  fi
  if [[ -n "$RETRY_GATES" ]]; then
    record "prerequisite installation" SKIP "retry mode reuses installed prerequisites"
    export PATH="/usr/lib/postgresql/17/bin:$PATH"
  else
    install_prerequisites
  fi
  for required in uv docker psql pg_dump pg_restore curl; do
    if ! command -v "$required" >/dev/null 2>&1; then
      record "required command: $required" FAIL "missing"
    fi
  done
  if [[ $FAILED -ne 0 ]]; then
    write_report
    return 1
  fi

  configure_file_limit
  if [[ $FAILED -ne 0 ]]; then
    write_report
    return 1
  fi

  if gate_enabled smoke || gate_enabled backup_restore || gate_enabled guess_sustained \
    || gate_enabled guess_burst || gate_enabled sockets_2000 || gate_enabled reconnect_1000 \
    || gate_enabled redis_recovery || gate_enabled app_restart; then
    start_local_validation
  else
    record "local validation stack" SKIP "not required by selected retry gates"
  fi
  if gate_enabled quality; then
    run_gate "quality suite" quality env DJANGO_SETTINGS_MODULE=config.settings.test \
      uv run python scripts/check.py
  else
    record "quality suite" SKIP "not selected by RETRY_GATES"
  fi
  if gate_enabled security; then
    run_gate "security suite" security uv run python scripts/check_security.py
  else
    record "security suite" SKIP "not selected by RETRY_GATES"
  fi
  run_image_gate
  if gate_enabled smoke; then
    run_gate "beta smoke" smoke env BASE_URL="$BASE_URL" "$ROOT_DIR/scripts/smoke_beta.sh"
  else
    record "beta smoke" SKIP "not selected by RETRY_GATES"
  fi
  run_restore_drill
  run_load_profiles
  run_local_resilience_drills
  write_report
  return "$FAILED"
}

main "$@"
