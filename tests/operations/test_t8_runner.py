from pathlib import Path

RUNNER = Path(__file__).parents[2] / "scripts" / "run_t8_validation.sh"


def test_t8_runner_has_safe_isolated_restore_and_private_artifacts() -> None:
    source = RUNNER.read_text()

    assert "think_fast_restore_validation_" in source
    assert 'RESTORE_CONFIRM_DATABASE="$RESTORE_DB"' in source
    assert 'DROP DATABASE IF EXISTS \\"$RESTORE_DB\\" WITH (FORCE)' in source
    assert 'chmod 600 "$FIXTURE_FILE"' in source
    assert "fixture contents must not be shared" in source
    assert "ALLOW_REMOTE_DB_DRILL=${ALLOW_REMOTE_DB_DRILL:-false}" in source
    assert "down --volumes" in source


def test_t8_runner_covers_every_required_capacity_profile() -> None:
    source = RUNNER.read_text()

    for profile in (
        "guess_sustained",
        "guess_burst",
        "sockets_2000",
        "reconnect_1000",
    ):
        assert profile in source
    assert "load-fixtures-$profile.json" in source
    assert "shred --remove" in source
    assert "RETRY_GATES" in source
    assert "not selected by RETRY_GATES" in source
    assert "REQUIRED_NOFILE=${REQUIRED_NOFILE:-65536}" in source
    assert 'ulimit -Sn "$REQUIRED_NOFILE"' in source
    assert "app-fd-sockets_2000.log" in source
    assert "stale validation cleanup" in source
    assert "^think-fast-t8-[0-9]+$" in source
    assert "LOAD_FIXTURE_START_BASE" in source


def test_t8_runner_measures_capacity_with_debug_off_and_pool_bounded() -> None:
    source = RUNNER.read_text()

    # Capacity must be measured with DEBUG off (Django otherwise retains every SQL
    # query on the connection) and with the psycopg pool explicitly enabled, so the
    # connection-exhaustion path that produced the Guess-load failures cannot recur.
    assert "export DJANGO_DEBUG=${DJANGO_DEBUG:-false}" in source
    assert "export POSTGRES_POOL_ENABLED=${POSTGRES_POOL_ENABLED:-true}" in source
    # The report must state the configuration each run measured.
    assert "Capacity config:" in source
    assert "pool_max=" in source
    # Live backend count must be sampled during each profile: holding 2,000 sockets
    # must not drive 2,000 PostgreSQL backends. This is the recorded pool evidence.
    assert "db-connections-$profile.log" in source
    assert "pg_stat_activity" in source


def test_t8_runner_does_not_claim_local_capacity_as_production_evidence() -> None:
    source = RUNNER.read_text()

    assert "not production capacity evidence" in source
    assert "does not by itself close the production staging capacity gate" in source
    assert "refusing to test an unknown process" in source
    assert "LOCAL_APP_READY" in source


def test_t8_runner_covers_image_and_recovery_drills() -> None:
    source = RUNNER.read_text()

    assert "production image build" in source
    assert "production image scan" in source
    assert "Redis failure/recovery" in source
    assert "application restart/recovery" in source
    assert "publish_outbox" in source
    assert "ghcr.io/aquasecurity/trivy-db:2" in source
    assert "postgresql-client-17" in source
    assert "--access-log /dev/null" in source
    assert '"$ROOT_DIR/.venv/bin/daphne"' in source
    assert '--skip-dirs "**/sboms"' in source
    assert '--skip-files "**/sboms/**"' in source
    assert "production image inventory" in source
    assert "--entrypoint /app/.venv/bin/python" in source
    assert "REUSE_IMAGE_TAG" in source


def test_socket_capacity_profile_is_single_attempt_per_vu() -> None:
    source = (Path(__file__).parents[2] / "tests" / "load" / "k6_beta.js").read_text()

    assert 'executor: "per-vu-iterations"' in source
    assert "vus: 2000" in source
    assert "iterations: 1" in source
    assert "constant-vus" not in source
    assert "SOCKET_RAMP_SECONDS" in source
    assert "socketRampSeconds" in source


def test_production_image_cannot_copy_the_host_virtualenv() -> None:
    source = (Path(__file__).parents[2] / "Dockerfile").read_text()

    assert "COPY --chown=appuser:appuser . ." not in source
    assert "COPY --chown=appuser:appuser config ./config" in source
    assert "COPY --chown=appuser:appuser apps ./apps" in source


def test_t8_runner_writes_a_report_from_cleanup_after_early_failure() -> None:
    source = RUNNER.read_text()

    assert "REPORT_WRITTEN=0" in source
    assert "write_report || true" in source
    assert "obsolete config/settings.py found" in source
    assert "${HOME}/.local/bin" in source
