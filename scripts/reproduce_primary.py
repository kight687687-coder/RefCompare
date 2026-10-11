"""Recompute primary results from the released frozen DOI inputs (no API calls)."""
from pathlib import Path
import argparse
import json
import sys

DISCIPLINES = ("computer_science", "medicine", "history", "physics", "economics")


def reproduce(package: Path, output: Path):
    sys.path.insert(0, str(package / "software/src"))
    from refcompare.pipeline import calculate_tables
    from refcompare.networks import build_graph_edges
    for discipline in DISCIPLINES:
        print(f"Primary analysis: {discipline}", flush=True)
        snapshots = json.loads((package / "primary_inputs" / discipline / "raw/snapshots.json").read_text("utf-8"))
        tables = calculate_tables(snapshots, {"damping": .85, "tolerance": 1e-8, "max_iter": 100, "top_fraction": .1})
        destination = output / discipline
        destination.mkdir(parents=True, exist_ok=True)
        for name, frame in tables.items():
            frame.to_csv(destination / f"{name}.csv", index=False, encoding="utf-8-sig")
        seeds = tables["reference_metrics"].query("comparison_group == 'comparable_both_doi_sets_nonempty'")
        graphs = build_graph_edges(seeds, {w["doi"]: w for w in snapshots["openalex_works"]}, snapshots["crossref_records"], snapshots["citing_by_seed"])
        for name, edges in graphs.items():
            edges.to_csv(destination / f"{name}_edges.csv", index=False, encoding="utf-8-sig")
        print(f"  clean seeds: {len(seeds)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, default=Path("recomputed/primary"))
    args = parser.parse_args()
    reproduce(args.package_root, args.output)
