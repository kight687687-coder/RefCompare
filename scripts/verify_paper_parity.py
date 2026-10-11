"""Verify the tool against saved study inputs and outputs without API calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from refcompare import __version__
from refcompare.pipeline import calculate_tables
from refcompare.networks import GRAPH_NAMES, build_graph_edges
from refcompare.identifiers import normalize_doi

RUNS = {
    "computer_science": "baseline_20260903",
    "medicine": "full_20260907",
    "history": "full_20260908",
    "physics": "full_20261004",
    "economics": "full_20261004",
}
GRAPH_MAP = dict(zip(GRAPH_NAMES, ("graph_openalex", "graph_crossref", "graph_shared")))


def load_inputs(root: Path, legacy: bool):
    oa_path = root / "raw/openalex" / ("样本清单.json" if legacy else "openalex_seed_works.json")
    cr_path = root / "raw/crossref" / ("元数据.jsonl" if legacy else "crossref_work_metadata.jsonl")
    works = json.loads(oa_path.read_text(encoding="utf-8"))["works"]
    # Study snapshots contain successful OA records without per-record HTTP status.
    works = [{**work, "doi": normalize_doi(work["doi"]), "status_code": work.get("status_code", 200)} for work in works]
    crossref = {item["doi"]: item for line in cr_path.read_text(encoding="utf-8").splitlines() if line.strip() for item in [json.loads(line)]}
    citing = {}
    cache_root = root / "raw/openalex" / ("citing缓存" if legacy else "openalex_citing_cache")
    for work in works:
        cache = cache_root / f"{work['id'].rsplit('/', 1)[-1]}.jsonl"
        if cache.is_file():
            citing[work["doi"]] = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"seed_dois": [work["doi"] for work in works], "openalex_works": works, "crossref_records": crossref, "citing_by_seed": citing}


def verify(study_root: Path, output: Path, disciplines: list[str]):
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    def check(discipline, name, passed, **details):
        checks.append({"discipline": discipline, "check": name, "passed": bool(passed), **details})

    for discipline in disciplines:
        print(f"Verifying {discipline}", flush=True)
        root = study_root / "02_最终结果" / discipline / RUNS[discipline]
        legacy = discipline == "computer_science"
        snapshots = load_inputs(root, legacy)
        tables = calculate_tables(snapshots, {})
        clean = tables["reference_metrics"].query("comparison_group == 'comparable_both_doi_sets_nonempty'")
        clean_path = next((root / "results_legacy").glob("*RCR*.csv")) if legacy else root / "results/clean_comparable_sample.csv"
        expected_clean = pd.read_csv(clean_path)
        check(discipline, "clean_seed_dois", set(clean.doi) == set(expected_clean.doi), actual_count=len(clean), expected_count=len(expected_clean))
        reference_columns = ["openalex_doi_reference_count", "crossref_doi_reference_count", "shared_reference_count", "union_reference_count", "rcr_openalex", "rcr_crossref", "jaccard_similarity"]
        actual_ref = clean.set_index("doi").sort_index()
        expected_ref = expected_clean.set_index("doi").sort_index()
        for column in reference_columns:
            if column in expected_ref:
                matched = actual_ref.index.equals(expected_ref.index) and np.allclose(actual_ref[column], expected_ref[column], rtol=1e-12, atol=1e-12)
                check(discipline, f"reference_metrics:{column}", matched)
        graphs = build_graph_edges(clean, {w["doi"]: w for w in snapshots["openalex_works"]}, snapshots["crossref_records"], snapshots["citing_by_seed"])
        saved_eligible_scores = {}
        for name, graph in graphs.items():
            saved_graph = GRAPH_MAP[name]
            edge_path = root / (f"networks_legacy/{name}_边表.csv" if legacy else f"networks/{saved_graph}_edges.csv")
            node_path = root / (f"networks_legacy/{name}_节点表.csv" if legacy else f"networks/{saved_graph}_nodes.csv")
            expected_edges = pd.read_csv(edge_path)
            actual_edges = set(graph.itertuples(index=False, name=None))
            saved_edges = set(expected_edges.itertuples(index=False, name=None))
            check(discipline, f"edges:{name}", actual_edges == saved_edges, actual_count=len(actual_edges), expected_count=len(saved_edges), missing_count=len(saved_edges-actual_edges), extra_count=len(actual_edges-saved_edges))
            actual_nodes = set(graph.source_doi) | set(graph.target_doi) | set(clean.doi)
            expected_nodes = set(pd.read_csv(node_path).doi)
            check(discipline, f"nodes:{name}", actual_nodes == expected_nodes, actual_count=len(actual_nodes), expected_count=len(expected_nodes))
            scores_path = root / (f"results_legacy/{name}_ASP分数.csv" if legacy else f"results/asp_scores_{saved_graph}.csv")
            expected_scores = pd.read_csv(scores_path, float_precision="round_trip").set_index("doi")["asp"].sort_index()
            reference_targets = set(expected_edges.loc[expected_edges.edge_type.isin(["reference", "shared_reference", "参考文献"]), "target_doi"])
            saved_eligible_scores[saved_graph if not legacy else name] = expected_scores.loc[expected_scores.index.isin(reference_targets)]
            actual_scores = tables["asp_scores"].query("graph == @name").set_index("doi")["asp_score"].sort_index()
            same_nodes = actual_scores.index.equals(expected_scores.index)
            max_error = float(np.max(np.abs(actual_scores.values - expected_scores.values))) if same_nodes else None
            check(discipline, f"asp:{name}", same_nodes and np.allclose(actual_scores, expected_scores, rtol=1e-10, atol=1e-14), max_abs_error=max_error)
        ranking_path = root / ("results_legacy/参考文献三对排名一致性汇总.csv" if legacy else "results/ranking_agreement_referenced_works.csv")
        expected_rank = pd.read_csv(ranking_path)
        actual_rank = tables["ranking_agreement"].copy()
        if not legacy:
            actual_rank["left_graph"] = actual_rank.left_graph.map(GRAPH_MAP)
            actual_rank["right_graph"] = actual_rank.right_graph.map(GRAPH_MAP)
        actual_rank = actual_rank.set_index(["left_graph", "right_graph"])
        field_map = {"kendall_tau_b": "kendall_tau", "top_fraction_n": "top_n", "top_fraction_overlap_count": "overlap_count", "top_fraction_overlap_rate": "overlap_rate_left"}
        for row in expected_rank.to_dict("records"):
            pair = (row["left_graph"], row["right_graph"])
            actual_row = actual_rank.loc[pair]
            common = saved_eligible_scores[pair[0]].index.intersection(saved_eligible_scores[pair[1]].index)
            orders = [series.loc[common].sort_index().sort_values(ascending=False, kind="stable") for series in (saved_eligible_scores[pair[0]], saved_eligible_scores[pair[1]])]
            # Historical exports used arbitrary row order at some tied cutoffs.
            # Benchmark the manuscript's explicit DOI rule against saved scores.
            for prefix, k, count_field, rate_field in (("top_fraction", max(1, int(.1*len(common))), "overlap_count", "overlap_rate_left"), ("top10", min(10, len(common)), "top10_overlap_count", "top10_agreement_rate"), ("top20", min(20, len(common)), "top20_overlap_count", "top20_agreement_rate")):
                overlap = len(set(orders[0].head(k).index) & set(orders[1].head(k).index))
                row[count_field], row[rate_field] = overlap, overlap/k if k else 0.0
            for column in tables["ranking_agreement"].select_dtypes("number").columns:
                saved_column = field_map.get(column, column)
                if saved_column not in row:
                    continue
                actual, expected = actual_row[column], row[saved_column]
                check(discipline, f"ranking:{pair[0]}:{pair[1]}:{column}", np.isclose(actual, expected, rtol=1e-10, atol=1e-10, equal_nan=True), actual=float(actual), expected=float(expected))
        run_output = output / discipline
        run_output.mkdir(exist_ok=True)
        for name in ("analysis_scope", "graph_statistics", "ranking_agreement"):
            tables[name].to_csv(run_output / f"{name}.csv", index=False, encoding="utf-8-sig")
    frame = pd.DataFrame(checks)
    frame.to_csv(output / "checks.csv", index=False, encoding="utf-8-sig")
    failures = frame.loc[~frame.passed]
    summary = {"tool_version": __version__, "network_requests": 0, "study_root": str(study_root.resolve()), "disciplines": disciplines, "check_count": len(frame), "failure_count": len(failures), "passed": failures.empty}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "README.md").write_text(
        f"# Paper parity verification\n\nTool version: {__version__}. No API calls.\n\n"
        "Inputs are the original study seed, Crossref, and citing-cache snapshots. Missing OA status_code is adapted to 200 because these files contain successfully retrieved records. No source datasets or published result tables are overwritten. Fixed Top-k benchmarks are independently reconstructed from saved scores using score descending / DOI ascending, because historical exports used arbitrary row order at some tied cutoffs. All other historical benchmarks are unchanged.\n\n"
        f"Checked {len(frame)} comparisons; {len(failures)} failures. Exact sets are required for clean DOI, edge and node checks. ASP allows rtol=1e-10, atol=1e-14 for CSV precision; ranking measures allow rtol=atol=1e-10.\n\n"
        + frame.groupby("discipline").passed.agg(["count", "sum"]).to_string()
        + "\n\nDetailed evidence: checks.csv; per-discipline analysis_scope, graph_statistics and ranking_agreement tables.\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    if not failures.empty:
        print(failures.to_string(index=False), flush=True)
    return 0 if failures.empty else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disciplines", nargs="+", choices=list(RUNS), default=list(RUNS))
    args = parser.parse_args()
    raise SystemExit(verify(args.study_root, args.output, args.disciplines))
