import pandas as pd

from refcompare.report import render_markdown_report


def test_report_explains_metrics_and_limits():
    tables = {
        "reference_metrics": pd.DataFrame([{"comparison_group": "comparable_both_doi_sets_nonempty", "jaccard_similarity": 0.5, "rcr_openalex": 0.8, "rcr_crossref": 0.7}]),
        "reference_groups": pd.DataFrame([{"comparison_group": "comparable_both_doi_sets_nonempty", "article_count": 1, "share": 1.0}]),
        "ranking_agreement": pd.DataFrame([{"left_graph": "Graph_OA", "right_graph": "Graph_CR", "common_node_count": 10, "kendall_tau_b": 0.7, "spearman_rho": 0.8, "top_fraction_overlap_rate": 0.5, "rank_displacement_mean": 2.0}]),
    }
    report = render_markdown_report({"input_doi_count": 1, "status": "completed"}, tables)
    assert "shared DOI references divided by the union" in report
    assert "Kendall tau-b summarizes rank-order agreement" in report
    assert "submitted seed set" in report
    assert "do not establish that either database is universally superior" in report


def test_report_marks_api_failure_separately_from_empty_references():
    tables = {
        "reference_metrics": pd.DataFrame([{"comparison_group": "crossref_404_or_request_failure"}]),
        "reference_groups": pd.DataFrame([{"comparison_group": "crossref_404_or_request_failure", "article_count": 1, "share": 1.0}]),
        "ranking_agreement": pd.DataFrame(),
    }
    report = render_markdown_report({"input_doi_count": 1, "status": "partial"}, tables)
    assert "failures rather than treating them as empty reference lists" in report
    assert "crossref_404_or_request_failure" in report
