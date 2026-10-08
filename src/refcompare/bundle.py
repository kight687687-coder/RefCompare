"""Versioned, credential-free run bundle storage."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__

SCHEMA_VERSION = 1
_SECRET_KEYS = re.compile(r"(?:api[_-]?key|mailto|email|authorization|token|password|secret)", re.IGNORECASE)
_SECRET_VALUE = re.compile(r"(?i)(mailto|api_key|authorization|token|password|secret)(=|%3D)[^&\s]+")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SECRET_KEYS.search(str(key)) else _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(r"\1\2[REDACTED]", value)
    return value


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write an atomic manifest, removing credential values recursively."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = _sanitize({"schema_version": SCHEMA_VERSION, "tool_version": __version__, **manifest})
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(clean, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_manifest(path: Path) -> dict[str, Any]:
    """Validate bundle schema and all source snapshot paths."""
    path = Path(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported run bundle schema: {manifest.get('schema_version')}")
    root = path.parent.resolve()
    for relative in manifest.get("snapshots", {}).values():
        candidate = (path.parent / relative).resolve()
        if root not in candidate.parents:
            raise ValueError("Run manifest refers to a snapshot outside the bundle")
        if not candidate.is_file():
            raise FileNotFoundError(f"Required snapshot is missing: {PurePosixPath(str(relative))}")
    return manifest
