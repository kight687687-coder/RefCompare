"""Construct controlled one-hop citation graph variants."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .identifiers import normalize_doi

GRAPH_NAMES = ("Graph_OA", "Graph_CR", "Graph_Shared")
EDGE_COLUMNS = ["source_doi", "target_doi", "edge_type"]


def add_edge(edges: set[tuple[str, str, str]], source: str, target: str, edge_type: str) -> None:
    source_doi = normalize_doi(source)
    target_doi = normalize_doi(target)
    if source_doi and target_doi and source_doi != target_doi:
        edges.add((source_doi, target_doi, edge_type))


def _refs(work: dict[str, Any]) -> set[str]:
    return {normalized for value in work.get("referenced_dois", []) if (normalized := normalize_doi(value))}


def _crossref_refs(record: dict[str, Any]) -> set[str]:
    refs = (record.get("message") or {}).get("reference") or []
    return {
        normalized
        for ref in refs
        if isinstance(ref, dict) and (normalized := normalize_doi(ref.get("DOI")))
    }


def build_graph_edges(
    seed_rows: pd.DataFrame,
    openalex_by_doi: dict[str, dict[str, Any]],
    crossref_by_doi: dict[str, dict[str, Any]],
    citing_by_seed: dict[str, list[dict[str, Any]]],
) -> dict[str, pd.DataFrame]:
    edges: dict[str, set[tuple[str, str, str]]] = {name: set() for name in GRAPH_NAMES}
    for value in seed_rows.get("doi", []):
        seed = normalize_doi(value)
        if not seed:
            continue
        oa = _refs(openalex_by_doi.get(seed, {}))
        cr = _crossref_refs(crossref_by_doi.get(seed, {}))
        for ref in oa:
            add_edge(edges["Graph_OA"], seed, ref, "reference")
        for ref in cr:
            add_edge(edges["Graph_CR"], seed, ref, "reference")
        for ref in oa & cr:
            add_edge(edges["Graph_Shared"], seed, ref, "shared_reference")
        for citing in citing_by_seed.get(seed, []):
            citing_doi = normalize_doi(citing.get("doi"))
            if citing_doi:
                for name in GRAPH_NAMES:
                    add_edge(edges[name], citing_doi, seed, "citing")
    return {
        name: pd.DataFrame(sorted(rows), columns=EDGE_COLUMNS)
        for name, rows in edges.items()
    }


def graph_statistics(graphs: dict[str, pd.DataFrame], seed_dois: set[str]) -> pd.DataFrame:
    rows = []
    for name, frame in graphs.items():
        nodes = set(frame.get("source_doi", [])) | set(frame.get("target_doi", [])) | seed_dois
        rows.append({
            "graph": name,
            "node_count": len(nodes),
            "edge_count": len(frame),
            "reference_edge_count": int(frame["edge_type"].isin(["reference", "shared_reference"]).sum()) if not frame.empty else 0,
            "citing_edge_count": int((frame["edge_type"] == "citing").sum()) if not frame.empty else 0,
            "seed_node_count": len(seed_dois & nodes),
        })
    return pd.DataFrame(rows)
