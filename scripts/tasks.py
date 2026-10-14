"""Portable Make command runner; all subprocess failures stop the task."""

import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    """Run a command from the repository root and propagate failure."""
    executable = shutil.which(args[0])
    if executable is None:
        raise SystemExit(f"Missing tool: {args[0]}. See README.md prerequisites.")
    print("+ " + " ".join(args), flush=True)
    subprocess.run([executable, *args[1:]], cwd=ROOT, check=True)


def main() -> None:
    """Dispatch the Makefile target."""
    npm = "npm.cmd" if os.name == "nt" else "npm"
    target = sys.argv[1]
    match target:
        case "setup":
            run("uv", "sync", "--project", "backend", "--frozen")
            run(npm, "ci", "--prefix", "frontend")
        case "up":
            run("docker", "compose", "up", "--build", "--detach", "--wait", "--wait-timeout", "180")
        case "down":
            run("docker", "compose", "down")
        case "lint":
            run(
                "uv",
                "run",
                "--project",
                "backend",
                "ruff",
                "check",
                "backend",
                "data",
                "ml",
                "scripts",
            )
            run(
                "uv",
                "run",
                "--project",
                "backend",
                "ruff",
                "format",
                "--check",
                "backend",
                "data",
                "ml",
                "scripts",
            )
            run(
                "uv",
                "run",
                "--project",
                "backend",
                "mypy",
                "--config-file",
                "backend/pyproject.toml",
                "backend/app",
                "data",
                "ml",
                "scripts",
            )
            run(npm, "--prefix", "frontend", "run", "lint")
            run(npm, "--prefix", "frontend", "run", "typecheck")
        case "test":
            run(
                "uv",
                "run",
                "--project",
                "backend",
                "pytest",
                "-c",
                "backend/pyproject.toml",
                "backend/tests/unit",
            )
            os.environ["TEST_POSTGRES_PASSWORD"] = secrets.token_urlsafe(24)
            try:
                run("docker", "compose", "--profile", "test", "up", "--detach", "--wait", "test-db")
                run("docker", "compose", "--profile", "test", "run", "--rm", "--build", "test-api")
            finally:
                run("docker", "compose", "--profile", "test", "rm", "--stop", "--force", "test-db")
            run(npm, "--prefix", "frontend", "test")
        case "migrate":
            run("docker", "compose", "exec", "-T", "api", "alembic", "upgrade", "head")
        case "seed":
            run("docker", "compose", "exec", "-T", "api", "alembic", "upgrade", "head")
            run("docker", "compose", "exec", "-T", "api", "python", "-m", "app.services.seed")
        case "build":
            run(npm, "--prefix", "frontend", "run", "build")
        case "smoke":
            run("uv", "run", "--project", "backend", "python", "scripts/smoke.py")
        case "types":
            run("uv", "run", "--project", "backend", "python", "scripts/export_types.py")
        case "hooks":
            run("uv", "run", "--project", "backend", "pre-commit", "install")
        case "train":
            raise SystemExit("train is not implemented until M2; see docs/BUILD_PLAN.md.")
        case _:
            raise SystemExit(f"Unknown task: {target}")


if __name__ == "__main__":
    main()
