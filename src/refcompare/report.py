"""Stable CSV exports and an English plain-language interpretation report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def write_csv_outputs(tables: dict[str, pd.DataFrame], output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, frame in tables.items():
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        paths.append(path)
    return paths


def _number(value: Any, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "not available"
    return f"{float(value):.{digits}f}"


def render_markdown_report(manifest: dict[str, Any], tables: dict[str, pd.DataFrame]) -> str:
    references = tables.get("reference_metrics", pd.DataFrame())
    groups = tables.get("reference_groups", pd.DataFrame())
    rankings = tables.get("ranking_agreement", pd.DataFrame())
    seed_count = int(manifest.get("input_doi_count", manifest.get("seed_doi_count", len(references))))
    comparable_count = int((references.get("comparison_group", pd.Series(dtype=str)) == "comparable_both_doi_sets_nonempty").sum())
    scope = tables.get("analysis_scope", pd.DataFrame())
    lines = [
        "# RefCompare results",
        "",
        "## What was analyzed",
        "",
        f"The run included **{seed_count} submitted seed DOI(s)**. A seed DOI identifies a work whose references were compared. **{comparable_count}** records had DOI-resolved references available from both sources and could be compared directly.",
        "",
    ]
    if not scope.empty:
        selected = scope.iloc[0]
        graph_description = "clean-comparable seeds" if selected["graph_scope"] == "clean-comparable" else "all analyzed seed records"
        ranking_description = "pairwise common referenced works, identified by reference-edge targets in both graphs" if selected["ranking_scope"] == "common-references" else "all pairwise common network nodes, including seed and citing roles"
        lines.extend([f"Network construction used **{int(selected['network_seed_count'])} {graph_description}**. ASP was computed on each full network; ranking comparisons used **{ranking_description}**.", ""])
        if not int(selected["network_seed_count"]):
            lines.extend(["No seeds qualified for the selected network scope; no network rankings are available. The analysis does not fall back to a broader scope.", ""])
    if manifest.get("status") in {"partial", "failed"}:
        lines.extend([f"Run status: **{manifest['status']}**. Some API records could not be retrieved; the tables retain these cases as failures rather than treating them as empty reference lists.", ""])
    elif manifest.get("source_status") in {"partial", "failed"}:
        lines.extend([f"Source retrieval status: **{manifest['source_status']}**. Offline analysis reuses these incomplete snapshots; no additional API records were fetched.", ""])
    if not groups.empty:
        lines.extend(["### Retrieval and comparison groups", "", "| Record state | Works | Share |", "|---|---:|---:|"])
        for row in groups.to_dict("records"):
            lines.append(f"| {row.get('comparison_group', 'unknown')} | {int(row.get('article_count', 0))} | {_number(row.get('share'), 1)} |")
        lines.append("")
    lines.extend([
        "## Reference-list differences",
        "",
        "For records with DOI-resolved references in both sources, the Jaccard similarity is the number of shared DOI references divided by the union of references observed in either source. A value closer to 1 means the two observed DOI sets overlap more. The reference coverage ratio (RCR) for each source is that source's DOI-reference count divided by the same observed union. These measures describe DOI-resolved observed sets; they do not estimate all references that exist in the underlying works.",
        "",
    ])
    if comparable_count:
        comparable = references[references["comparison_group"] == "comparable_both_doi_sets_nonempty"]
        jaccard = comparable["jaccard_similarity"].dropna()
        oa_rcr = comparable["rcr_openalex"].dropna()
        cr_rcr = comparable["rcr_crossref"].dropna()
        lines.append(f"Among the {comparable_count} directly comparable record(s), median Jaccard similarity was **{_number(jaccard.median() if len(jaccard) else None)}**. Median observed-union RCR was **{_number(oa_rcr.median() if len(oa_rcr) else None)}** for OpenAlex and **{_number(cr_rcr.median() if len(cr_rcr) else None)}** for Crossref.")
    else:
        lines.append("No seed had DOI-resolved reference sets from both sources, so no direct reference-set similarity summary is available.")
    lines.extend(["", "## Ranking impact", "", "ASP is a local prestige-style score calculated within each constructed one-hop network. The three networks vary the reference edges (OpenAlex, Crossref, or shared references) while keeping the retrieved citing-work edges the same. ASP values should be interpreted within this constructed sample, not as absolute scholarly prestige.", ""])
    if rankings.empty or not rankings["common_node_count"].gt(0).any():
        lines.append("Ranking comparisons were unavailable because no objects qualified in both graphs under the selected ranking scope.")
    else:
        lines.extend(["| Graph comparison | Common works | Kendall tau-b | Spearman rho | Top-fraction overlap | Mean rank displacement |", "|---|---:|---:|---:|---:|---:|"])
        for row in rankings.to_dict("records"):
            comparison = f"{row.get('left_graph', '?')} vs {row.get('right_graph', '?')}"
            lines.append(f"| {comparison} | {int(row.get('common_node_count', 0))} | {_number(row.get('kendall_tau_b'))} | {_number(row.get('spearman_rho'))} | {_number(row.get('top_fraction_overlap_rate'), 1)} | {_number(row.get('rank_displacement_mean'))} |")
        lines.append("")
        if len(rankings):
            row = rankings.iloc[0]
            lines.append(f"Kendall tau-b summarizes rank-order agreement (higher positive values mean more similar orderings). Top-fraction overlap is the share of works that appear in both networks' highest-scoring group. Mean absolute rank displacement is the average number of rank positions by which common works move. For the first comparison shown, these were **{_number(row.get('kendall_tau_b'))}**, **{_number(row.get('top_fraction_overlap_rate'), 1)}**, and **{_number(row.get('rank_displacement_mean'))}**, respectively.")
    lines.extend([
        "",
        "## How to read these findings",
        "",
        "These results describe only the submitted seed set and the OpenAlex/Crossref records retrieved for this run. DOI matching can miss references recorded without a DOI or with an unresolved DOI. API snapshots change over time. The ranking analysis is limited to a one-hop network and uses the same retrieved citing works across graph variants. Therefore, the results do not establish that either database is universally superior.",
        "",
        "See the CSV files beside this report for per-seed details, graph statistics, scores, and pairwise ranking changes. The run manifest records the method settings and retrieval status.",
        "",
    ])
    return "\n".join(lines)


def write_report(manifest: dict[str, Any], tables: dict[str, pd.DataFrame], output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.md"
    path.write_text(render_markdown_report(manifest, tables), encoding="utf-8")
    return path
