import pandas as pd

from refcompare.networks import build_graph_edges


def test_graphs_separate_reference_sets_and_share_citing_edges():
    seed_rows = pd.DataFrame([{"doi": "10.1000/seed", "comparison_group": "comparable_both_doi_sets_nonempty"}])
    openalex_by_doi = {"10.1000/seed": {"referenced_dois": ["10.1000/a", "10.1000/shared"]}}
    crossref_by_doi = {"10.1000/seed": {"message": {"reference": [{"DOI": "10.1000/b"}, {"DOI": "10.1000/shared"}]}}}
    citing_by_seed = {"10.1000/seed": [{"doi": "10.1000/citing"}]}
    graphs = build_graph_edges(seed_rows, openalex_by_doi, crossref_by_doi, citing_by_seed)
    oa = set(map(tuple, graphs["Graph_OA"].to_numpy()))
    cr = set(map(tuple, graphs["Graph_CR"].to_numpy()))
    shared = set(map(tuple, graphs["Graph_Shared"].to_numpy()))
    assert ("10.1000/seed", "10.1000/a", "reference") in oa
    assert ("10.1000/seed", "10.1000/b", "reference") in cr
    assert ("10.1000/seed", "10.1000/shared", "shared_reference") in shared
    citing = ("10.1000/citing", "10.1000/seed", "citing")
    assert citing in oa and citing in cr and citing in shared


def test_empty_graphs_have_stable_columns():
    graphs = build_graph_edges(pd.DataFrame(columns=["doi"]), {}, {}, {})
    assert all(list(frame.columns) == ["source_doi", "target_doi", "edge_type"] for frame in graphs.values())
