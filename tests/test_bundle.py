import json

import pytest

from refcompare.bundle import read_manifest, write_manifest


def test_manifest_redacts_credentials(tmp_path):
    path = tmp_path / "run_manifest.json"
    write_manifest(path, {"mailto": "private@example.org", "settings": {"api_key": "secret-value"}})
    content = path.read_text(encoding="utf-8")
    assert "private@example.org" not in content
    assert "secret-value" not in content
    assert json.loads(content)["settings"]["api_key"] == "[REDACTED]"


def test_manifest_rejects_snapshot_escape(tmp_path):
    path = tmp_path / "run_manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "snapshots": {"bad": "../secret.json"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the bundle"):
        read_manifest(path)
