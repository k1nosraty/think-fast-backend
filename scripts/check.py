"""Run every local/CI quality gate in a stable order."""

import subprocess
import sys

COMMANDS = [
    ["ruff", "format", "--check", "."],
    ["ruff", "check", "."],
    ["mypy", "apps", "config"],
    ["python", "manage.py", "check", "--settings=config.settings.test"],
    [
        "python",
        "manage.py",
        "makemigrations",
        "--check",
        "--dry-run",
        "--settings=config.settings.test",
    ],
    ["python", "scripts/validate_contracts.py"],
    ["pytest"],
]


def main() -> int:
    for command in COMMANDS:
        print(f"+ {' '.join(command)}", flush=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
