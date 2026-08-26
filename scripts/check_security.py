"""Run production configuration and dependency/static security gates."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = Path(os.getenv("SECURITY_CACHE_DIR", "/tmp/think-fast-security-cache"))


def run(command: list[str], *, environment: dict[str, str] | None = None) -> int:
    print(f"+ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode


def main() -> int:
    production_env = {
        **os.environ,
        "DJANGO_SECRET_KEY": "security-check-only-" + "x" * 64,
        "DJANGO_ALLOWED_HOSTS": "api.example.test",
        "POSTGRES_PASSWORD": "security-check-only",
        "REDIS_URL": "redis://127.0.0.1:6379/15",
        "GAME_SECRET_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "METRICS_BEARER_TOKEN": "security-check-only-" + "x" * 32,
    }
    commands = [
        (
            [
                "python",
                "manage.py",
                "check",
                "--deploy",
                "--settings=config.settings.production",
            ],
            production_env,
        ),
        (
            [
                "bandit",
                "-q",
                "-r",
                "apps",
                "config",
                "-x",
                "*/tests/*,*/migrations/*,config/settings/local.py,config/settings/test.py",
                "-ll",
            ],
            None,
        ),
        (
            ["pip-audit", "--local", "--cache-dir", str(CACHE_DIR / "pip-audit")],
            None,
        ),
    ]
    for command, environment in commands:
        if run(command, environment=environment):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
