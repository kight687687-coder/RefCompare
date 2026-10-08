import pytest

from refcompare.references import compare_seed_references


def test_reference_set_metrics_use_shared_union_denominator():
    row = compare_seed_references(
        {"doi": "10.1000/seed", "status_code": 200, "referenced_works": ["W1", "W2"], "referenced_dois": ["10.1000/a", "10.1000/b"]},
        {"status_code": 200, "message": {"reference": [{"DOI": "10.1000/a"}, {"DOI": "10.1000/c"}]}},
    )
    assert row["shared_reference_count"] == 1
    assert row["union_reference_count"] == 3
    assert row["jaccard_similarity"] == pytest.approx(1 / 3)
    assert row["rcr_openalex"] == pytest.approx(2 / 3)
    assert row["rcr_crossref"] == pytest.approx(2 / 3)
    assert row["comparison_group"] == "comparable_both_doi_sets_nonempty"


def test_empty_crossref_and_failed_request_are_distinct():
    work = {"doi": "10.1000/seed", "status_code": 200, "referenced_works": ["W1"], "referenced_dois": ["10.1000/a"]}
    empty = compare_seed_references(work, {"status_code": 200, "message": {"reference": []}})
    failed = compare_seed_references(work, {"status_code": None, "error": "network failure"})
    assert empty["comparison_group"] == "crossref_200_reference_empty"
    assert failed["comparison_group"] == "crossref_404_or_request_failure"


def test_unresolved_references_are_not_comparable():
    row = compare_seed_references(
        {"doi": "10.1000/seed", "status_code": 200, "referenced_works": ["W1"], "referenced_dois": []},
        {"status_code": 200, "message": {"reference": [{"unstructured": "Unknown source"}]}},
    )
    assert row["comparison_group"] == "crossref_200_reference_present_but_not_comparable"
