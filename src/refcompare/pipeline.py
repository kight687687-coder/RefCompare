"""Online acquisition and deterministic offline analysis orchestration."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from . import __version__
from .api import ApiSettings, ApiRequestError, CrossrefClient, OpenAlexClient
from .bundle import read_manifest, write_manifest
from .identifiers import normalize_doi
from .metrics import compare_rankings, compute_asp
from .networks import GRAPH_NAMES, build_graph_edges, graph_statistics
from .references import analyze_reference_sets, reference_group_summary
from .report import write_report

DEFAULT_ANALYSIS_SETTINGS = {
    "graph_scope": "clean-comparable",
    "ranking_scope": "common-references",
}


def resolve_analysis_settings(overrides: dict[str, object] | None = None) -> dict[str, object]:
    settings = {**DEFAULT_ANALYSIS_SETTINGS, **(overrides or {})}
    if settings["graph_scope"] not in {"clean-comparable", "all-records"}:
        raise ValueError("graph_scope must be clean-comparable or all-records")
    if settings["ranking_scope"] not in {"common-references", "all-common-nodes"}:
        raise ValueError("ranking_scope must be common-references or all-common-nodes")
    return settings


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_snapshots(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "raw" / "snapshots.json").read_text(encoding="utf-8"))


def _save_snapshot_files(run_dir: Path, snapshots: dict[str, Any]) -> dict[str, str]:
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    openalex_path = raw_dir / "openalex_seed_works.json"
    crossref_path = raw_dir / "crossref_records.json"
    citing_path = raw_dir / "openalex_citing_works.json"
    _write_json(openalex_path, snapshots["openalex_works"])
    _write_json(crossref_path, snapshots["crossref_records"])
    _write_json(citing_path, snapshots["citing_by_seed"])
    _write_json(raw_dir / "snapshots.json", snapshots)
    return {
        "openalex": "raw/openalex_seed_works.json",
        "crossref": "raw/crossref_records.json",
        "citing": "raw/openalex_citing_works.json",
        "all_snapshots": "raw/snapshots.json",
    }


def run_online(
    dois: list[str],
    output_dir: Path,
    settings: ApiSettings,
    asp_settings: dict[str, object],
    analysis_settings: dict[str, object] | None = None,
) -> Path:
    """Fetch user-selected seed works and return the completed run manifest path."""
    output_dir = Path(output_dir)
    analysis_settings = resolve_analysis_settings(analysis_settings)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_dois = list(dict.fromkeys(filter(None, (normalize_doi(value) for value in dois))))
    if not clean_dois:
        raise ValueError("At least one valid DOI is required")
    started = datetime.now(timezone.utc).isoformat()
    manifest_path = output_dir / "run_manifest.json"
    manifest: dict[str, Any] = {
        "run_id": output_dir.name,
        "status": "running",
        "started_at_utc": started,
        "input_doi_count": len(clean_dois),
        "asp_settings": asp_settings,
        "analysis_settings": analysis_settings,
        "snapshots": {},
        "api_counts": {"openalex_success": 0, "openalex_failure": 0, "crossref_success": 0, "crossref_failure": 0, "citing_success": 0, "citing_failure": 0},
    }
    write_manifest(manifest_path, manifest)
    openalex_client = OpenAlexClient(settings)
    crossref_client = CrossrefClient(settings)
    openalex_works: list[dict[str, Any]] = []
    crossref_records: dict[str, dict[str, Any]] = {}
    citing_by_seed: dict[str, list[dict[str, Any]]] = {}
    for index, doi in enumerate(clean_dois, start=1):
        print(f"Fetching seed {index}/{len(clean_dois)}: {doi}")
        try:
            work = openalex_client.get_work(doi)
            work["doi"] = normalize_doi(work.get("doi") or doi)
            work["status_code"] = 200
            openalex_works.append(work)
            manifest["api_counts"]["openalex_success"] += 1
        except ApiRequestError as exc:
            openalex_works.append({"doi": doi, "status_code": exc.status_code, "error": str(exc), "referenced_works": [], "referenced_dois": []})
            manifest["api_counts"]["openalex_failure"] += 1
        try:
            record = crossref_client.get_work(doi)
            crossref_records[doi] = record
            if record.get("status_code") == 200:
                manifest["api_counts"]["crossref_success"] += 1
            else:
                manifest["api_counts"]["crossref_failure"] += 1
        except ApiRequestError as exc:
            crossref_records[doi] = {"doi": doi, "status_code": None, "error": str(exc)}
            manifest["api_counts"]["crossref_failure"] += 1
        time.sleep(0.05)

    valid_works = [work for work in openalex_works if work.get("status_code") == 200]
    ref_ids = sorted({ref for work in valid_works for ref in work.get("referenced_works", []) if isinstance(ref, str)})
    try:
        reference_map = openalex_client.get_reference_dois(ref_ids)
    except ApiRequestError as exc:
        reference_map = {}
        manifest["reference_resolution_error"] = str(exc)
    for work in valid_works:
        work["referenced_dois"] = [reference_map.get(ref.rsplit("/", 1)[-1]) for ref in work.get("referenced_works", []) if reference_map.get(ref.rsplit("/", 1)[-1])]

    for index, work in enumerate(valid_works, start=1):
        doi = normalize_doi(work.get("doi"))
        if not doi:
            continue
        try:
            citing_by_seed[doi] = openalex_client.fetch_citing_works(work)
            manifest["api_counts"]["citing_success"] += 1
        except ApiRequestError as exc:
            citing_by_seed[doi] = []
            manifest["api_counts"]["citing_failure"] += 1
            manifest.setdefault("citing_errors", {})[doi] = str(exc)
        print(f"Fetched citing records {index}/{len(valid_works)}: {doi}")

    snapshots = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed_dois": clean_dois,
        "openalex_works": openalex_works,
        "crossref_records": crossref_records,
        "citing_by_seed": citing_by_seed,
    }
    manifest["snapshots"] = _save_snapshot_files(output_dir, snapshots)
    manifest["source_retrieved_at_utc"] = snapshots["retrieved_at_utc"]
    manifest["status"] = "completed" if not manifest["api_counts"]["openalex_failure"] and not manifest["api_counts"]["crossref_failure"] and not manifest["api_counts"]["citing_failure"] else "partial"
    manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["tool_version"] = __version__
    tables = calculate_tables(snapshots, asp_settings, analysis_settings)
    outputs = write_tables(output_dir, tables, manifest)
    manifest["outputs"] = {key: str(path.relative_to(output_dir)) for key, path in outputs.items()}
    write_manifest(manifest_path, manifest)
    return manifest_path


def calculate_tables(
    snapshots: dict[str, Any], asp_settings: dict[str, object],
    analysis_settings: dict[str, object] | None = None,
) -> dict[str, pd.DataFrame]:
    """Score full graphs, then compare pairwise eligible ranking objects."""
    analysis_settings = resolve_analysis_settings(analysis_settings)
    openalex_works = snapshots.get("openalex_works", [])
    openalex_by_doi = {doi: work for work in openalex_works if (doi := normalize_doi(work.get("doi"))) and work.get("status_code") == 200}
    crossref_by_doi = snapshots.get("crossref_records", {})
    references = analyze_reference_sets(openalex_works, crossref_by_doi)
    seed_rows = references if not references.empty else pd.DataFrame(columns=["doi", "comparison_group"])
    if analysis_settings["graph_scope"] == "clean-comparable":
        seed_rows = seed_rows.loc[seed_rows["comparison_group"] == "comparable_both_doi_sets_nonempty"]
    graphs = build_graph_edges(seed_rows, openalex_by_doi, crossref_by_doi, snapshots.get("citing_by_seed", {}))
    seed_dois = set(seed_rows["doi"])
    graph_stats = graph_statistics(graphs, seed_dois)
    scores: dict[str, pd.Series] = {}
    asp_rows: list[dict[str, Any]] = []
    for graph_name in GRAPH_NAMES:
        edges = graphs[graph_name]
        nodes = set(edges.get("source_doi", [])) | set(edges.get("target_doi", [])) | seed_dois
        score, status = compute_asp(
            edges,
            nodes,
            damping=float(asp_settings.get("damping", 0.85)),
            tolerance=float(asp_settings.get("tolerance", 1e-8)),
            max_iter=int(asp_settings.get("max_iter", 100)),
        )
        asp_rows.extend({"graph": graph_name, "doi": doi, "asp_score": value, **status} for doi, value in score.items())
        if analysis_settings["ranking_scope"] == "common-references":
            referenced_dois = set(edges.loc[edges["edge_type"].isin(["reference", "shared_reference"]), "target_doi"])
            score = score.loc[score.index.isin(referenced_dois)]
        scores[graph_name] = score
    ranking_summary, ranking_details = compare_rankings(scores, float(asp_settings.get("top_fraction", 0.10)))
    for frame in (ranking_summary, ranking_details):
        frame["graph_scope"] = analysis_settings["graph_scope"]
        frame["ranking_scope"] = analysis_settings["ranking_scope"]
    ranking_summary["left_eligible_work_count"] = ranking_summary["left_graph"].map(lambda name: len(scores[name]))
    ranking_summary["right_eligible_work_count"] = ranking_summary["right_graph"].map(lambda name: len(scores[name]))
    return {
        "analysis_scope": pd.DataFrame([{
            **analysis_settings, "submitted_seed_count": len(references),
            "clean_comparable_seed_count": int((references.get("comparison_group", pd.Series(dtype=str)) == "comparable_both_doi_sets_nonempty").sum()),
            "network_seed_count": len(seed_dois),
        }]),
        "reference_metrics": references,
        "reference_groups": reference_group_summary(references),
        "graph_statistics": graph_stats,
        "asp_scores": pd.DataFrame(asp_rows, columns=["graph", "doi", "asp_score", "iterations", "converged", "max_change"]),
        "ranking_agreement": ranking_summary,
        "ranking_details": ranking_details,
    }


def write_tables(
    output_dir: Path, tables: dict[str, pd.DataFrame], manifest: dict[str, Any] | None = None
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    for name, frame in tables.items():
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        outputs[name] = path
    outputs["summary"] = write_report(manifest or {}, tables, output_dir)
    return outputs


def run_offline(
    input_dir: Path,
    output_dir: Path | None = None,
    asp_overrides: dict[str, object] | None = None,
    analysis_overrides: dict[str, object] | None = None,
) -> Path:
    input_dir = Path(input_dir)
    source_manifest_path = input_dir / "run_manifest.json"
    source_manifest = read_manifest(source_manifest_path)
    snapshot_path = input_dir / source_manifest["snapshots"]["all_snapshots"]
    snapshots = json.loads(snapshot_path.read_text(encoding="utf-8"))
    destination = Path(output_dir) if output_dir else input_dir / "reanalyzed"
    destination.mkdir(parents=True, exist_ok=True)
    asp_settings = {**source_manifest.get("asp_settings", {}), **(asp_overrides or {})}
    analysis_settings = resolve_analysis_settings({**source_manifest.get("analysis_settings", {}), **(analysis_overrides or {})})
    tables = calculate_tables(snapshots, asp_settings, analysis_settings)
    manifest = {
        "run_id": destination.name,
        "status": "completed",
        "source_run": str(input_dir.resolve()),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed_doi_count": len(snapshots.get("seed_dois", [])),
        "asp_settings": asp_settings,
        "analysis_settings": analysis_settings,
        "source_retrieved_at_utc": snapshots.get("retrieved_at_utc"),
        "source_status": source_manifest.get("source_status", source_manifest.get("status")),
    }
    # A reanalysis is a reusable bundle too, including the exact source snapshots.
    manifest["snapshots"] = _save_snapshot_files(destination, snapshots)
    outputs = write_tables(destination, tables, manifest)
    manifest["outputs"] = {key: str(path.relative_to(destination)) for key, path in outputs.items()}
    manifest_path = destination / "run_manifest.json"
    write_manifest(manifest_path, manifest)
    return manifest_path
