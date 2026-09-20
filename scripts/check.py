"""Run every local/CI quality gate in a stable order."""

import os
import subprocess
import sys

COMMANDS = [
    ["ruff", "format", "--check", "."],
    ["ruff", "check", "."],
    ["mypy", "apps", "config"],
    [sys.executable, "manage.py", "check", "--settings=config.settings.test"],
    [
        sys.executable,
        "manage.py",
        "makemigrations",
        "--check",
        "--dry-run",
        "--settings=config.settings.test",
    ],
    [sys.executable, "scripts/validate_contracts.py"],
    ["pytest"],
]


def main() -> int:
    test_environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.test"}
    for command in COMMANDS:
        print(f"+ {' '.join(command)}", flush=True)
        completed = subprocess.run(command, check=False, env=test_environment)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
