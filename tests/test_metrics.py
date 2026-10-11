import pandas as pd

from refcompare.metrics import compare_rankings, compute_asp


def test_asp_assigns_more_score_to_cited_node():
    edges = pd.DataFrame([{"source_doi": "10.1000/source", "target_doi": "10.1000/target"}])
    scores, status = compute_asp(edges, ["10.1000/source", "10.1000/target"])
    assert scores["10.1000/target"] > scores["10.1000/source"]
    assert status["converged"] is True


def test_empty_asp_graph_returns_uniform_scores():
    scores, status = compute_asp(pd.DataFrame(columns=["source_doi", "target_doi"]), ["a", "b"])
    assert scores.to_dict() == {"a": 0.5, "b": 0.5}
    assert status["converged"] is True


def test_rank_comparison_uses_only_common_objects():
    summary, details = compare_rankings({"Graph_OA": pd.Series({"a": 0.9, "b": 0.1}), "Graph_CR": pd.Series({"b": 0.8, "c": 0.2})})
    assert set(details["doi"]) == {"b"}
    assert summary.loc[0, "common_node_count"] == 1
    assert pd.isna(summary.loc[0, "kendall_tau_b"])


def test_rank_overlap_is_clipped_to_common_count():
    scores = {"Graph_OA": pd.Series({"a": 4.0, "b": 3.0, "c": 2.0}), "Graph_CR": pd.Series({"a": 4.0, "b": 3.0, "c": 2.0})}
    summary, _ = compare_rankings(scores)
    assert summary.loc[0, "top_fraction_n"] == 1
    assert summary.loc[0, "top_fraction_overlap_count"] == 1


def test_cutoff_ties_are_deterministic_when_input_order_changes():
    left = pd.Series({"c": 1.0, "b": 1.0, "a": 1.0, "d": 0.5})
    right = pd.Series({"a": 2.0, "b": 1.0, "c": 1.0, "d": 0.4})
    first, _ = compare_rankings({"OA": left, "CR": right}, top_fraction=0.5)
    second, _ = compare_rankings({"OA": left.iloc[::-1], "CR": right}, top_fraction=0.5)
    assert first.loc[0, "top_fraction_overlap_count"] == 2
    assert second.loc[0, "top_fraction_overlap_count"] == 2
    assert first.loc[0, "top_fraction_tie_expanded_left_size"] == 3
    assert first.loc[0, "top_fraction_tie_expanded_right_size"] == 3
    assert first.loc[0, "top_fraction_tie_expanded_jaccard"] == 1.0


def test_absolute_cutoff_membership_uses_doi_order_and_keeps_all_cutoff_ties():
    scores = pd.Series({f"doi-{i:02d}": 1.0 for i in range(12, 0, -1)})
    summary, details = compare_rankings({"OA": scores, "CR": scores.iloc[::-1]})
    expected = {f"doi-{i:02d}" for i in range(1, 11)}
    assert set(details.loc[details.left_top10, "doi"]) == expected
    assert set(details.loc[details.right_top10, "doi"]) == expected
    assert summary.loc[0, "top10_tie_expanded_left_size"] == 12
    assert summary.loc[0, "top10_tie_expanded_right_size"] == 12
    assert summary.loc[0, "top10_tie_expanded_jaccard"] == 1.0
