from pathlib import Path

from refcompare.identifiers import normalize_doi, read_doi_file


def test_normalize_doi_removes_prefix_and_case():
    assert normalize_doi(" https://doi.org/10.1234/AbC ") == "10.1234/abc"


def test_normalize_doi_rejects_non_doi():
    assert normalize_doi("not-a-doi") is None


def test_read_doi_file_reports_invalid_and_duplicate_rows(tmp_path: Path):
    path = tmp_path / "dois.txt"
    path.write_text("10.1234/ABC\nhttps://doi.org/10.1234/abc\nbad\n", encoding="utf-8")
    dois, rows = read_doi_file(path)
    assert dois == ["10.1234/abc"]
    assert [row["status"] for row in rows] == ["valid", "duplicate", "invalid"]
