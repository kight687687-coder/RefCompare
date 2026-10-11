"""Reference-set comparison and record-level coverage metrics."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .identifiers import normalize_doi, normalize_record_doi


def _reference_dois(message: dict[str, Any]) -> list[object]:
    return [reference.get("DOI") for reference in (message.get("reference") or []) if isinstance(reference, dict)]


def _classify(openalex_work: dict[str, Any], crossref_record: dict[str, Any], oa_set: set[str], cr_set: set[str]) -> str:
    if openalex_work.get("status_code") != 200:
        return "openalex_404" if openalex_work.get("status_code") == 404 else "openalex_request_failure"
    status = crossref_record.get("status_code")
    if status != 200:
        return "crossref_404_or_request_failure"
    message = crossref_record.get("message") or {}
    references = message.get("reference") or []
    if not references:
        return "crossref_200_reference_empty"
    if (openalex_work.get("referenced_works") or []) and oa_set and cr_set:
        return "comparable_both_doi_sets_nonempty"
    return "crossref_200_reference_present_but_not_comparable"


def compare_seed_references(openalex_work: dict[str, Any], crossref_record: dict[str, Any]) -> dict[str, Any]:
    doi = normalize_doi(openalex_work.get("doi") or crossref_record.get("doi"))
    oa_values = openalex_work.get("referenced_dois") or []
    crossref_message = crossref_record.get("message") or {}
    cr_values = _reference_dois(crossref_message)
    oa_set = {normalized for value in oa_values if (normalized := normalize_record_doi(value))}
    cr_set = {normalized for value in cr_values if (normalized := normalize_record_doi(value))}
    shared = oa_set & cr_set
    oa_only = oa_set - cr_set
    cr_only = cr_set - oa_set
    union = oa_set | cr_set
    denominator = len(union)
    status = crossref_record.get("status_code")
    return {
        "doi": doi,
        "title": openalex_work.get("title"),
        "publication_year": openalex_work.get("publication_year"),
        "openalex_type": openalex_work.get("type"),
        "crossref_status_code": status,
        "openalex_reference_field_present": bool(openalex_work.get("referenced_works") or []),
        "crossref_reference_field_present": status == 200 and bool(crossref_message.get("reference") or []),
        "openalex_doi_reference_count": len(oa_set),
        "crossref_raw_reference_count": len(crossref_message.get("reference") or []) if status == 200 else 0,
        "crossref_doi_reference_count": len(cr_set),
        "shared_reference_count": len(shared),
        "openalex_observed_exclusive_count": len(oa_only),
        "crossref_observed_exclusive_count": len(cr_only),
        "union_reference_count": denominator,
        "jaccard_similarity": len(shared) / denominator if denominator else None,
        "rcr_openalex": len(oa_set) / denominator if denominator else None,
        "rcr_crossref": len(cr_set) / denominator if denominator else None,
        "comparison_group": _classify(openalex_work, crossref_record, oa_set, cr_set),
        "openalex_observed_exclusive_dois": "|".join(sorted(oa_only)),
        "crossref_observed_exclusive_dois": "|".join(sorted(cr_only)),
    }


def analyze_reference_sets(
    openalex_works: list[dict[str, Any]], crossref_records: dict[str, dict[str, Any]]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for work in openalex_works:
        doi = normalize_doi(work.get("doi"))
        if not doi:
            continue
        row = compare_seed_references(work, crossref_records.get(doi, {"doi": doi, "status_code": None}))
        rows.append(row)
    return pd.DataFrame(rows)


def reference_group_summary(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "comparison_group" not in rows:
        return pd.DataFrame(columns=["comparison_group", "article_count", "share"])
    counts = rows["comparison_group"].value_counts(dropna=False).rename_axis("comparison_group").reset_index(name="article_count")
    counts["share"] = counts["article_count"] / len(rows)
    return counts
