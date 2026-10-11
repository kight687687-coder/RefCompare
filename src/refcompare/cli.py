"""Command-line interface for RefCompare."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from .api import ApiSettings
from .identifiers import read_doi_file
from .pipeline import run_offline, run_online


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refcompare",
        description="Compare OpenAlex and Crossref reference sets and ranking impact.",
        epilog="Online runs require a Crossref contact email. Offline analysis reads a saved RefCompare run bundle without contacting APIs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="fetch API data and analyze a DOI list")
    run.add_argument("--dois", type=Path, required=True, help="UTF-8 text file with one DOI per line")
    run.add_argument("--output", type=Path, required=True, help="directory for the reusable run bundle and outputs")
    run.add_argument("--mailto", default=os.getenv("CROSSREF_MAILTO"), help="your contact email for Crossref (or set CROSSREF_MAILTO)")
    run.add_argument("--openalex-api-key", default=os.getenv("OPENALEX_API_KEY"), help="optional OpenAlex API key (or set OPENALEX_API_KEY)")
    run.add_argument("--damping", type=float, default=0.85, help="ASP damping value (default: 0.85)")
    run.add_argument("--tolerance", type=float, default=1e-8, help="ASP convergence tolerance (default: 1e-8)")
    run.add_argument("--max-iter", type=int, default=100, help="maximum ASP iterations (default: 100)")
    run.add_argument("--top-fraction", type=float, default=0.10, help="fraction for top-group overlap (default: 0.10)")
    analyze = subparsers.add_parser("analyze", help="reanalyze a saved bundle without network access")
    analyze.add_argument("--input-dir", type=Path, required=True, help="directory created by an earlier refcompare run")
    analyze.add_argument("--output", type=Path, help="optional directory for reanalysis outputs; defaults to INPUT_DIR/reanalyzed")
    analyze.add_argument("--damping", type=float)
    analyze.add_argument("--tolerance", type=float)
    analyze.add_argument("--max-iter", type=int)
    analyze.add_argument("--top-fraction", type=float)
    for command in (run, analyze):
        command.add_argument("--graph-scope", choices=("clean-comparable", "all-records"), help="network seeds (default: clean-comparable; offline inherits saved setting)")
        command.add_argument("--ranking-scope", choices=("common-references", "all-common-nodes"), help="pairwise comparison objects (default: common-references; offline inherits saved setting)")
    return parser


def _non_none_options(args: argparse.Namespace) -> dict[str, object]:
    return {key: value for key in ("damping", "tolerance", "max_iter", "top_fraction") if (value := getattr(args, key, None)) is not None}


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        if args.command == "run":
            if not args.mailto:
                print("Error: Crossref email is required. Pass --mailto or set CROSSREF_MAILTO.", file=sys.stderr)
                return 2
            if args.damping < 0 or args.damping >= 1:
                print("Error: --damping must be in [0, 1).", file=sys.stderr)
                return 2
            if args.tolerance <= 0 or args.max_iter <= 0 or not 0 < args.top_fraction <= 1:
                print("Error: tolerance and max-iter must be positive; top-fraction must be in (0, 1].", file=sys.stderr)
                return 2
            dois, rows = read_doi_file(args.dois)
            invalid_count = sum(row["status"] == "invalid" for row in rows)
            duplicate_count = sum(row["status"] == "duplicate" for row in rows)
            print(f"Validated {len(dois)} unique DOI(s); {duplicate_count} duplicate(s), {invalid_count} invalid row(s).")
            if not dois:
                print("Error: the file contains no valid DOI.", file=sys.stderr)
                return 2
            settings = ApiSettings(args.mailto, args.openalex_api_key)
            analysis_options = {key: getattr(args, key) for key in ("graph_scope", "ranking_scope") if getattr(args, key) is not None}
            manifest = run_online(dois, args.output, settings, _non_none_options(args), analysis_options)
            print(f"Finished. Run manifest: {manifest}")
            print(f"Results report: {manifest.parent / 'summary.md'}")
            return 0
        overrides = _non_none_options(args)
        analysis_options = {key: getattr(args, key) for key in ("graph_scope", "ranking_scope") if getattr(args, key) is not None}
        manifest = run_offline(args.input_dir, args.output, overrides, analysis_options)
        print(f"Offline analysis finished. Run manifest: {manifest}")
        print(f"Results report: {manifest.parent / 'summary.md'}")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
