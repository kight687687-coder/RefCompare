import json

import pytest

from refcompare.bundle import write_manifest
from refcompare.api import ApiSettings
from refcompare.pipeline import run_offline, run_online


@pytest.fixture
def offline_bundle(tmp_path):
    root = tmp_path / "original_run"
    raw = root / "raw"
    raw.mkdir(parents=True)
    snapshots = {
        "retrieved_at_utc": "2026-01-01T00:00:00+00:00",
        "seed_dois": ["10.1000/seed"],
        "openalex_works": [{"doi": "10.1000/seed", "status_code": 200, "referenced_works": ["W1"], "referenced_dois": ["10.1000/ref"]}],
        "crossref_records": {"10.1000/seed": {"doi": "10.1000/seed", "status_code": 200, "message": {"reference": [{"DOI": "10.1000/ref"}]}}},
        "citing_by_seed": {"10.1000/seed": [{"doi": "10.1000/citing"}]},
    }
    (raw / "snapshots.json").write_text(json.dumps(snapshots), encoding="utf-8")
    write_manifest(root / "run_manifest.json", {"status": "completed", "asp_settings": {}, "snapshots": {"all_snapshots": "raw/snapshots.json"}})
    return root


def test_offline_run_never_calls_api(tmp_path, monkeypatch, offline_bundle):
    def fail(*args, **kwargs):
        raise AssertionError("offline analysis attempted a network request")

    monkeypatch.setattr("requests.Session.get", fail)
    manifest = run_offline(offline_bundle, output_dir=tmp_path / "rerun")
    assert manifest.exists()
    assert (tmp_path / "rerun" / "reference_metrics.csv").exists()
    assert (tmp_path / "rerun" / "ranking_agreement.csv").exists()


def test_online_run_writes_reusable_bundle_with_mocked_api(tmp_path, monkeypatch):
    class FakeOpenAlex:
        def __init__(self, settings):
            pass

        def get_work(self, doi):
            return {"id": "https://openalex.org/W1", "doi": doi, "title": "Seed", "status_code": 200, "referenced_works": ["https://openalex.org/W2"]}

        def get_reference_dois(self, work_ids):
            return {"W2": "https://doi.org/10.1000/ref"}

        def fetch_citing_works(self, work):
            return [{"doi": "https://doi.org/10.1000/citing"}]

    class FakeCrossref:
        def __init__(self, settings):
            pass

        def get_work(self, doi):
            return {"doi": doi, "status_code": 200, "message": {"reference": [{"DOI": "10.1000/ref"}]}}

    monkeypatch.setattr("refcompare.pipeline.OpenAlexClient", FakeOpenAlex)
    monkeypatch.setattr("refcompare.pipeline.CrossrefClient", FakeCrossref)
    monkeypatch.setattr("refcompare.pipeline.time.sleep", lambda _: None)
    output = tmp_path / "online"
    manifest_path = run_online(["10.1000/seed"], output, ApiSettings("reader@example.org", "secret-key"), {})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["snapshots"]["all_snapshots"] == "raw/snapshots.json"
    assert (output / "raw" / "snapshots.json").is_file()
    assert (output / "summary.md").is_file()
    serialized = "".join(path.read_text(encoding="utf-8", errors="ignore") for path in output.rglob("*.*") if path.is_file())
    assert "reader@example.org" not in serialized
    assert "secret-key" not in serialized
