"""Verify committed sources in a fresh clone and isolated disposable Compose project."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def free_port(start: int) -> int:
    """Find an available loopback port without using Windows' ephemeral port range."""
    for port in range(start, start + 100):
        with socket.socket() as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free verification port")


def main() -> None:
    """Clone, run the documented workflow, exercise a DB outage, and remove own volumes."""
    git = shutil.which("git")
    make = shutil.which("make")
    docker = shutil.which("docker")
    if git is None or make is None or docker is None:
        raise SystemExit("Git, Make, and Docker are required")
    revision = subprocess.check_output([git, "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    suffix = secrets.token_hex(4)
    project = f"gridwatch-clean-{suffix}"
    clone = ROOT / ".tooling" / project
    clone.parent.mkdir(exist_ok=True)
    subprocess.run([git, "clone", "--no-local", str(ROOT), str(clone)], check=True)
    api_port, web_port = free_port(18000), free_port(15173)
    config = (
        (clone / ".env.example")
        .read_text()
        .replace("change-me-local-only", secrets.token_urlsafe(32))
    )
    (clone / ".env").write_text(config)
    env = os.environ.copy()
    env.update(
        COMPOSE_PROJECT_NAME=project,
        COMPOSE_FILE=str(clone / "docker-compose.yml"),
        API_PORT=str(api_port),
        WEB_PORT=str(web_port),
    )
    receipt: dict[str, object] = {"revision": revision, "project": project, "clone": str(clone)}
    completed: list[str] = []
    receipt["passed"] = completed

    def run(*args: str) -> None:
        print("+ " + " ".join(args), flush=True)
        subprocess.run(args, cwd=clone, env=env, check=True)

    try:
        for target in ("setup", "up", "seed", "train", "test", "lint", "build", "smoke"):
            run(make, target)
            completed.append(f"make {target}")
        uv = shutil.which("uv")
        assert uv is not None
        run(uv, "run", "--project", "backend", "python", "-m", "data.generator.samples", "--check")
        env["GRIDWATCH_UPLOAD_ACCEPTANCE_URL"] = f"http://localhost:{api_port}"
        run(uv, "run", "--project", "backend", "python", "scripts/upload_acceptance.py")
        completed.append("synthetic samples and upload acceptance")
        run(docker, "compose", "stop", "db")
        with urlopen(f"http://localhost:{api_port}/health", timeout=10) as response:
            assert response.status == 200
        try:
            urlopen(f"http://localhost:{api_port}/api/v1/ready", timeout=10).close()
        except HTTPError as error:
            assert error.code == 503
        else:
            raise AssertionError("Readiness must fail while the database is stopped")
        run(docker, "compose", "start", "db")
        for _ in range(30):
            try:
                with urlopen(f"http://localhost:{api_port}/api/v1/ready", timeout=5) as response:
                    assert response.status == 200
                break
            except (OSError, HTTPError):
                time.sleep(1)
        else:
            raise AssertionError("Readiness did not recover after database restart")
        completed.append("database outage: live 200, ready 503, recovered ready 200")
        receipt["status"] = "passed"
    finally:
        run(docker, "compose", "down", "--volumes", "--remove-orphans")
        (ROOT / ".tooling" / "clean-clone-verification.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
