"""Input parsing and conservative DOI normalization."""

from __future__ import annotations

import re
from pathlib import Path

_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_PREFIX_PATTERN = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:)]}>\"'"


def normalize_doi(value: object) -> str | None:
    """Return a normalized DOI or ``None`` when the value is not DOI-shaped."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = _PREFIX_PATTERN.sub("", raw).strip().rstrip(_TRAILING_PUNCTUATION)
    if not _DOI_PATTERN.fullmatch(raw):
        return None
    return raw.lower()


def read_doi_file(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    """Read one DOI per line and retain a status row for every nonblank line."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"DOI input file does not exist: {path}")
    unique: list[str] = []
    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        original = line.strip()
        if not original or original.startswith("#"):
            continue
        doi = normalize_doi(original)
        if doi is None:
            status = "invalid"
        elif doi in seen:
            status = "duplicate"
        else:
            status = "valid"
            seen.add(doi)
            unique.append(doi)
        rows.append({"line_number": line_number, "original_value": original, "doi": doi, "status": status})
    if not rows:
        raise ValueError(f"No DOI entries found in input file: {path}")
    return unique, rows


def normalize_record_doi(value: object) -> str | None:
    """Apply the study's operational DOI rule to retrieved graph records.

    This preserves the study's observed identifiers, including malformed
    suffixes. It checks shape, not DOI registration or syntactic validity.
    User-supplied seed input continues to use normalize_doi's stricter rule.
    """
    if not isinstance(value, str):
        return None
    doi = _PREFIX_PATTERN.sub("", value.strip().lower()).strip().rstrip(".,;:)]}>")
    return doi if doi.startswith("10.") and "/" in doi else None
