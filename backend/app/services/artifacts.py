"""Versioned local artifacts; database registration follows successful file publication."""

import hashlib
import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import joblib

if TYPE_CHECKING:
    from ml.train import ModelBundle, TrainingResult

FILES = ("model.joblib", "metadata.json", "metrics.json", "evaluation.json")


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def version_path(root: Path, version: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", version):
        raise ValueError("Invalid artifact version")
    root = root.resolve()
    target = (root / version).resolve()
    if target.parent != root:
        raise ValueError("Artifact version must stay within the artifact directory")
    return target


def save_artifacts(
    root: Path, version: str, result: "TrainingResult", metadata: dict[str, object]
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = version_path(root, version)
    if target.exists():
        raise FileExistsError(f"Artifact version already exists: {version}")
    with TemporaryDirectory(prefix=".stage-", dir=root) as temporary:
        stage = Path(temporary)
        joblib.dump(result.bundle, stage / "model.joblib", compress=3)
        write_json(stage / "metadata.json", metadata)
        write_json(stage / "metrics.json", result.metrics)
        write_json(stage / "evaluation.json", result.report)
        write_json(
            stage / "manifest.json",
            {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in FILES},
        )
        os.rename(stage, target)
    return target


def verify_artifacts(root: Path, version: str) -> Path:
    """Check every artifact before use, including metadata-only model information requests."""
    target = version_path(root, version)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Artifact manifest must be an object of file checksums")
    for name in FILES:
        if hashlib.sha256((target / name).read_bytes()).hexdigest() != manifest.get(name):
            raise ValueError(f"Artifact checksum mismatch: {name}")
    return target


def load_artifacts(root: Path, version: str) -> "ModelBundle":
    """Load only trusted local joblib files; hashes detect corruption, not malicious writers."""
    from ml.train import ModelBundle

    target = verify_artifacts(root, version)
    bundle = joblib.load(target / "model.joblib")
    if not isinstance(bundle, ModelBundle):
        raise ValueError("Artifact does not contain a GridWatch model")
    return bundle


def remove_unregistered_artifacts(root: Path, version: str) -> None:
    """Remove only a newly created version after registration fails, never other runs."""
    target = version_path(root, version)
    for name in (*FILES, "manifest.json"):
        (target / name).unlink(missing_ok=True)
    target.rmdir()
