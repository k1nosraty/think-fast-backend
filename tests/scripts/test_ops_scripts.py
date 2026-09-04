"""Structural and validation tests for ops shell scripts.

These scripts (backup_postgres.sh, restore_postgres.sh, smoke_beta.sh) are
operational tooling, not production Python code.  The tests here verify:
  - valid bash syntax (bash -n)
  - required env-var enforcement
  - basic success-path behaviour (smoke_beta.sh with mocked curl)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _run(
    script: str,
    *,
    env: dict[str, str] | None = None,
    extra_path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    path = run_env.get("PATH", "")
    if extra_path is not None:
        run_env["PATH"] = f"{extra_path}:{path}"
    return subprocess.run(
        ["sh", str(SCRIPTS / script)],
        env=run_env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _mock_curl(
    tmp: Path,
    *,
    fail: bool = False,
    body: str = "",
) -> str:
    """Create a fake curl script under *tmp*/bin and return the dir."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    printf_line = f"printf '%s\\n' '{body}'\n"
    code = dedent(
        """\
        #!/usr/bin/env sh
        case "$1" in
          --fail|--silent|--show-error) shift ;;
        esac
        case "$1" in
          */health/live/|*/health/ready/) ;; esac
        """
        + ("exit 22\n" if fail else printf_line)
    )
    (bin_dir / "curl").write_text(code)
    (bin_dir / "curl").chmod(0o755)
    return str(bin_dir)


# ── Script existence & syntax ────────────────────────────────────────────────


class TestScriptStructure:
    @pytest.mark.parametrize(
        "name",
        ["backup_postgres.sh", "restore_postgres.sh", "smoke_beta.sh"],
    )
    def test_script_exists_and_executable(self, name: str) -> None:
        path = SCRIPTS / name
        assert path.exists(), f"{name} missing"
        assert os.access(path, os.X_OK), f"{name} not executable"

    @pytest.mark.parametrize(
        "name",
        ["backup_postgres.sh", "restore_postgres.sh", "smoke_beta.sh"],
    )
    def test_bash_syntax(self, name: str) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPTS / name)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"syntax error in {name}: {result.stderr}"


# ── backup_postgres.sh ──────────────────────────────────────────────────────

REQUIRED_BACKUP_ENV = {
    "POSTGRES_DB": "testdb",
    "POSTGRES_USER": "testuser",
    "POSTGRES_HOST": "localhost",
    "BACKUP_DIR": "/tmp/test-backup",
}


class TestBackupPostgres:
    @pytest.mark.parametrize("var", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_HOST", "BACKUP_DIR"])
    def test_missing_required_var_fails(self, var: str) -> None:
        env = {k: v for k, v in REQUIRED_BACKUP_ENV.items() if k != var}
        result = _run("backup_postgres.sh", env=env)
        assert result.returncode != 0
        assert var in result.stderr

    def test_default_port_applied(self) -> None:
        env = REQUIRED_BACKUP_ENV.copy()
        env.pop("POSTGRES_PORT", None)
        # Script should not fail on port validation (it has a default).
        # It fails later on pg_dump (no real DB), which is fine.
        result = _run("backup_postgres.sh", env=env)
        assert result.returncode != 0
        assert "POSTGRES_PORT" not in result.stderr


# ── restore_postgres.sh ─────────────────────────────────────────────────────


class TestRestorePostgres:
    def test_database_confirmation_mismatch(self) -> None:
        env = {
            "POSTGRES_DB": "production",
            "POSTGRES_USER": "u",
            "POSTGRES_HOST": "h",
            "RESTORE_FILE": "/nonexistent.dump",
            "RESTORE_CONFIRM_DATABASE": "wrong-db",
        }
        result = _run("restore_postgres.sh", env=env)
        assert result.returncode != 0
        assert "RESTORE_CONFIRM_DATABASE must exactly match" in result.stderr

    def test_missing_backup_file(self) -> None:
        env = {
            "POSTGRES_DB": "db",
            "POSTGRES_USER": "u",
            "POSTGRES_HOST": "h",
            "RESTORE_FILE": "/nonexistent.dump",
            "RESTORE_CONFIRM_DATABASE": "db",
        }
        result = _run("restore_postgres.sh", env=env)
        assert result.returncode != 0
        assert "Backup and matching .sha256 file are required" in result.stderr

    @pytest.mark.parametrize(
        "var",
        [
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_HOST",
            "RESTORE_FILE",
            "RESTORE_CONFIRM_DATABASE",
        ],
    )
    def test_missing_required_var_fails(self, var: str) -> None:
        env = {
            "POSTGRES_DB": "db",
            "POSTGRES_USER": "u",
            "POSTGRES_HOST": "h",
            "RESTORE_FILE": "/f.dump",
            "RESTORE_CONFIRM_DATABASE": "db",
        }
        env.pop(var)
        result = _run("restore_postgres.sh", env=env)
        assert result.returncode != 0


# ── smoke_beta.sh ────────────────────────────────────────────────────────────


class TestSmokeBeta:
    def test_success(self, tmp_path: Path) -> None:
        mock_dir = _mock_curl(tmp_path, body="ok")
        result = _run("smoke_beta.sh", env={"BASE_URL": "https://example.com"}, extra_path=mock_dir)
        assert result.returncode == 0
        assert "beta_smoke=passed" in result.stdout

    def test_missing_base_url(self) -> None:
        result = _run("smoke_beta.sh", env={})
        assert result.returncode != 0

    def test_failure_on_unhealthy_endpoint(self, tmp_path: Path) -> None:
        mock_dir = _mock_curl(tmp_path, fail=True)
        result = _run("smoke_beta.sh", env={"BASE_URL": "https://example.com"}, extra_path=mock_dir)
        assert result.returncode != 0
        assert "beta_smoke" not in result.stdout
