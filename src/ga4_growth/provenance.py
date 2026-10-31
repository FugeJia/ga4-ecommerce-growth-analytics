"""Provenance checks shared by batch and dashboard; hashes are not signatures."""

import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_input(path: Path) -> dict:
    sidecar = path.with_suffix(".manifest.json")
    if not sidecar.exists():
        raise ValueError("Input provenance sidecar is required")
    metadata = json.loads(sidecar.read_text())
    if metadata.get("data_mode") not in {"synthetic_demo", "bigquery_public"}:
        raise ValueError("Unrecognized data_mode")
    if metadata.get("sha256") != file_sha256(path):
        raise ValueError("Input hash does not match provenance sidecar")
    return metadata
