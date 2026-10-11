import json

import pytest
import pandas as pd

from refcompare.bundle import write_manifest
from refcompare.api import ApiSettings
from refcompare.pipeline import calculate_tables, run_offline, run_online


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


@pytest.fixture
def mixed_snapshots():
    def work(doi, refs, status=200):
        return {"doi": doi, "status_code": status, "referenced_works": ["W1"] if refs else [], "referenced_dois": refs}

    def record(refs, status=200):
        return {"status_code": status, "message": {"reference": [{"DOI": doi} for doi in refs]}}

    # ref2 is only a citing node in CR/Shared, so it cannot qualify there.
    # clean2 is also referenced: a DOI may have multiple roles in the paper.
    return {
        "seed_dois": ["10.1000/clean1", "10.1000/clean2", "10.1000/empty", "10.1000/failed", "10.1000/oa-failed"],
        "openalex_works": [
            work("10.1000/clean1", ["10.1000/ref1", "10.1000/ref2", "10.1000/clean2"]),
            work("10.1000/clean2", ["10.1000/ref3"]),
            work("10.1000/empty", ["10.1000/excluded"]),
            work("10.1000/failed", ["10.1000/excluded"]),
            work("10.1000/oa-failed", [], 404),
        ],
        "crossref_records": {
            "10.1000/clean1": record(["10.1000/ref1", "10.1000/clean2"]),
            "10.1000/clean2": record(["10.1000/ref3", "10.1000/cr-only"]),
            "10.1000/empty": record([]),
            "10.1000/failed": record(["10.1000/excluded"], 503),
            "10.1000/oa-failed": record(["10.1000/excluded"]),
        },
        "citing_by_seed": {
            "10.1000/clean1": [{"doi": "10.1000/ref2"}, {"doi": "10.1000/citing"}],
            "10.1000/empty": [{"doi": "10.1000/excluded-citing"}],
        },
    }


def test_paper_defaults_filter_seeds_and_pairwise_reference_roles(mixed_snapshots):
    tables = calculate_tables(mixed_snapshots, {})
    assert len(tables["reference_metrics"]) == 5
    assert tables["graph_statistics"]["seed_node_count"].tolist() == [2, 2, 2]
    assert set(tables["ranking_details"]["doi"]) == {"10.1000/ref1", "10.1000/ref3", "10.1000/clean2"}
    assert tables["ranking_agreement"]["common_node_count"].tolist() == [3, 3, 3]
    assert set(tables["asp_scores"]["doi"]) == {
        "10.1000/clean1", "10.1000/clean2", "10.1000/ref1", "10.1000/ref2",
        "10.1000/ref3", "10.1000/cr-only", "10.1000/citing",
    }
    assert tables["analysis_scope"].iloc[0]["network_seed_count"] == 2


def test_optional_scopes_retain_full_asp_and_restore_old_population(mixed_snapshots):
    paper = calculate_tables(mixed_snapshots, {})
    all_nodes = calculate_tables(mixed_snapshots, {}, {"ranking_scope": "all-common-nodes"})
    pd.testing.assert_frame_equal(paper["asp_scores"], all_nodes["asp_scores"])
    assert "10.1000/citing" in set(all_nodes["ranking_details"]["doi"])
    all_records = calculate_tables(mixed_snapshots, {}, {"graph_scope": "all-records", "ranking_scope": "all-common-nodes"})
    assert all_records["graph_statistics"]["seed_node_count"].tolist() == [5, 5, 5]
    assert "10.1000/excluded-citing" in set(all_records["asp_scores"]["doi"])


@pytest.mark.parametrize("empty_input", [False, True])
def test_no_clean_seeds_produces_empty_graphs_without_fallback(mixed_snapshots, empty_input):
    snapshots = {} if empty_input else {**mixed_snapshots, "crossref_records": {}}
    tables = calculate_tables(snapshots, {})
    assert tables["asp_scores"].empty
    assert tables["ranking_details"].empty
    assert tables["ranking_agreement"]["common_node_count"].tolist() == [0, 0, 0]
    assert tables["graph_statistics"]["node_count"].tolist() == [0, 0, 0]
    assert "doi" in tables["ranking_details"]


def test_disjoint_reference_sets_do_not_compare_common_seed_or_citing_nodes(offline_bundle):
    snapshots = json.loads((offline_bundle / "raw" / "snapshots.json").read_text())
    snapshots["crossref_records"]["10.1000/seed"]["message"]["reference"] = [{"DOI": "10.1000/different"}]
    tables = calculate_tables(snapshots, {})
    assert len(tables["asp_scores"]) > 0
    assert tables["ranking_details"].empty
    assert tables["ranking_agreement"]["common_node_count"].tolist() == [0, 0, 0]


def test_offline_defaults_inheritance_overrides_and_reusable_output(tmp_path, offline_bundle):
    default_path = run_offline(offline_bundle, tmp_path / "default")
    default = json.loads(default_path.read_text())
    assert default["analysis_settings"] == {"graph_scope": "clean-comparable", "ranking_scope": "common-references"}
    legacy_path = run_offline(offline_bundle, tmp_path / "legacy", analysis_overrides={"graph_scope": "all-records", "ranking_scope": "all-common-nodes"})
    inherited_path = run_offline(legacy_path.parent, tmp_path / "inherited")
    inherited = json.loads(inherited_path.read_text())
    assert inherited["analysis_settings"]["ranking_scope"] == "all-common-nodes"
    report = (inherited_path.parent / "summary.md").read_text()
    assert "all pairwise common network nodes" in report
    overridden_path = run_offline(inherited_path.parent, tmp_path / "overridden", analysis_overrides={"ranking_scope": "common-references"})
    assert json.loads(overridden_path.read_text())["analysis_settings"]["ranking_scope"] == "common-references"
    assert "pairwise common referenced works" in (default_path.parent / "summary.md").read_text()


@pytest.mark.parametrize("settings", [{"graph_scope": "bad"}, {"ranking_scope": "bad"}])
def test_invalid_analysis_scope_is_rejected(settings):
    with pytest.raises(ValueError, match="scope must be"):
        calculate_tables({}, {}, settings)
