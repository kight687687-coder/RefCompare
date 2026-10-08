# RefCompare Command-Line Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish an installable, understandable Python CLI that compares OpenAlex and Crossref references and reports the paper's ASP ranking-impact analysis.

**Architecture:** A clean `src/refcompare` package separates DOI inputs, API acquisition, reference-set metrics, graph/ASP analysis, run bundles, reports, and CLI orchestration. An online run saves all source snapshots needed for an offline reanalysis; both paths call the same deterministic analysis functions.

**Tech Stack:** Python 3.10+, `argparse`, `requests`, `pandas`, `numpy`, `scipy`, `pytest`, `pyproject.toml`, GitHub Actions.

## Global Constraints

- The supported runtime will be Python 3.10 or newer.
- The command line will use Python's standard `argparse` interface to keep installation light.
- The first release targets batches of up to a few dozen seed works.
- The Crossref email is provided by the user at run time or through an environment variable. An OpenAlex key is optional and is also supplied at run time or through an environment variable. Neither value is written to run manifests, logs, or checked-in files.
- ASP defaults are damping `0.85`, convergence tolerance `1e-8`, and maximum `100` iterations.
- Ranking defaults include Kendall tau-b, Spearman rho, absolute top-10/top-20 overlap and agreement, top-decile fraction `0.10`, and absolute displacement mean, median, P90, and shares at thresholds `5` and `10`.
- Paper-method settings are the defaults; advanced overrides are recorded in the manifest and report.
- ASP is described as a local score within the constructed one-hop network, not an absolute measure of scholarly prestige.
- The public repository contains no manuscript, research corpus, private raw results, or credentials.
- Tests must pass without live credentials or live API calls.

---

## File map

- `pyproject.toml`: package metadata, dependency bounds, pytest configuration, and `refcompare` console entry point.
- `src/refcompare/__init__.py`: package version.
- `src/refcompare/identifiers.py`: DOI normalization and DOI text-file parsing.
- `src/refcompare/api.py`: OpenAlex and Crossref HTTP clients, retry policy, and API response validation.
- `src/refcompare/bundle.py`: run manifest, raw snapshot persistence, and bundle validation.
- `src/refcompare/references.py`: seed/reference extraction, comparison groups, and reference-set metrics.
- `src/refcompare/networks.py`: the three reference graph variants and shared citing-work edges.
- `src/refcompare/metrics.py`: ASP and ranking comparison metrics.
- `src/refcompare/pipeline.py`: online acquisition and offline analysis orchestration.
- `src/refcompare/report.py`: CSV outputs and English Markdown interpretation.
- `src/refcompare/cli.py`: `run` and `analyze` commands, validation, progress, and human-readable errors.
- `tests/conftest.py`, `tests/fixtures/`: reusable synthetic responses and offline bundle fixture.
- `tests/test_*.py`: focused unit and integration tests.
- `README.md`, `README.zh-CN.md`: English-first and Chinese user instructions.
- `examples/seed_dois.txt`: a short, clearly labeled example.
- `LICENSE`: MIT license.
- `.github/workflows/tests.yml`: offline CI on Linux and Windows.

## Task 1: Create installable package and robust DOI input

**Files:**
- Create: `pyproject.toml`
- Create: `src/refcompare/__init__.py`
- Create: `src/refcompare/identifiers.py`
- Test: `tests/test_identifiers.py`

**Interfaces:**
- `normalize_doi(value: object) -> str | None`: returns a lowercase DOI without a DOI URL or `doi:` prefix; returns `None` for empty or invalid input.
- `read_doi_file(path: Path) -> tuple[list[str], list[dict[str, object]]]`: returns unique normalized DOIs in first-seen order and row-level records containing line number, original value, normalized DOI, and status (`valid`, `duplicate`, or `invalid`).

- [ ] **Step 1: Write failing normalization and input tests.**

```python
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
```

- [ ] **Step 2: Run the focused tests and verify they fail because the package is not implemented.**

Run: `python -m pytest tests/test_identifiers.py -q`
Expected: collection failure for the missing `refcompare` package.

- [ ] **Step 3: Add package metadata and the DOI functions.** Configure `refcompare = "refcompare.cli:main"`, declare Python `>=3.10`, and depend only on `requests`, `pandas`, `numpy`, and `scipy`. Implement DOI matching with `^10\.\d{4,9}/\S+$`, remove `https://doi.org/`, `http://doi.org/`, `https://dx.doi.org/`, and `doi:` prefixes case-insensitively, trim trailing punctuation, and preserve first-seen order while marking duplicates.

- [ ] **Step 4: Run the focused tests and verify they pass.**

Run: `python -m pytest tests/test_identifiers.py -q`
Expected: all three tests pass.

- [ ] **Step 5: Commit the package foundation.**

```text
git add pyproject.toml src/refcompare/__init__.py src/refcompare/identifiers.py tests/test_identifiers.py
git commit -m "feat: add package foundation and DOI parsing"
```

## Task 2: Add API clients and secret-safe raw snapshots

**Files:**
- Create: `src/refcompare/api.py`
- Create: `src/refcompare/bundle.py`
- Test: `tests/test_api.py`
- Test: `tests/test_bundle.py`

**Interfaces:**
- `ApiSettings(mailto: str, openalex_api_key: str | None = None, timeout_seconds: int = 60, max_attempts: int = 6)`.
- `request_json(session: requests.Session, url: str, params: dict[str, str], settings: ApiSettings) -> dict[str, object]`: retries HTTP 429 and 5xx plus request exceptions with bounded exponential backoff; raises `ApiRequestError` after the final attempt.
- `write_manifest(path: Path, manifest: dict[str, object]) -> None`: writes JSON after recursively excluding credential keys and URL query values containing API keys or email addresses.
- `read_manifest(path: Path) -> dict[str, object]`: validates schema version and referenced snapshot paths before offline use.

- [ ] **Step 1: Write failing tests with mocked sessions and secret checks.** Create `tests/test_api.py` with this contract:

```python
from unittest.mock import Mock

import pytest
import requests

from refcompare.api import ApiRequestError, ApiSettings, request_json


def test_request_json_retries_429_then_returns_payload():
    session = Mock(spec=requests.Session)
    session.get.side_effect = [Mock(status_code=429, headers={"Retry-After": "0"}), Mock(status_code=200, json=lambda: {"ok": True})]
    assert request_json(session, "https://example.test", {}, ApiSettings("a@example.org")) == {"ok": True}
    assert session.get.call_count == 2


def test_request_json_does_not_retry_not_found():
    session = Mock(spec=requests.Session)
    response = Mock(status_code=404)
    response.raise_for_status.side_effect = requests.HTTPError("404")
    session.get.return_value = response
    with pytest.raises(ApiRequestError):
        request_json(session, "https://example.test", {}, ApiSettings("a@example.org"))
    assert session.get.call_count == 1
```

Create `tests/test_bundle.py` with a test that writes a manifest containing an email and an API key, then asserts neither secret appears in the serialized file.
- [ ] **Step 2: Run `python -m pytest tests/test_api.py tests/test_bundle.py -q`; confirm failures identify the missing client and manifest functions.**
- [ ] **Step 3: Implement `ApiSettings`, `ApiRequestError`, bounded retries (maximum six attempts, delays capped at 30 seconds), `OpenAlexClient`, and `CrossrefClient`. Put user credentials only in request parameters or headers. Implement manifest schema version 1 and atomic JSON writes through a sibling temporary file followed by replace. Use this retry control flow:**

```python
for attempt in range(settings.max_attempts):
    try:
        response = session.get(url, params=params, timeout=settings.timeout_seconds)
        if response.status_code == 429 or response.status_code >= 500:
            if attempt + 1 == settings.max_attempts:
                response.raise_for_status()
            time.sleep(min(2**attempt, 30))
            continue
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ApiRequestError("API response must be a JSON object")
        return payload
    except requests.RequestException as exc:
        if attempt + 1 == settings.max_attempts:
            raise ApiRequestError(f"Request failed after {settings.max_attempts} attempts") from exc
        time.sleep(min(2**attempt, 30))
raise ApiRequestError("Request failed")
```
- [ ] **Step 4: Rerun `python -m pytest tests/test_api.py tests/test_bundle.py -q`; all mocked cases must pass without network access.**
- [ ] **Step 5: Commit with `git add src/refcompare/api.py src/refcompare/bundle.py tests/test_api.py tests/test_bundle.py` and `git commit -m "feat: add API clients and run manifests"`.**

## Task 3: Implement reference-set comparison and coverage outputs

**Files:**
- Create: `src/refcompare/references.py`
- Test: `tests/test_references.py`
- Create: `tests/fixtures/openalex_seed_works.json`
- Create: `tests/fixtures/crossref_records.jsonl`

**Interfaces:**
- `compare_seed_references(openalex_work: dict, crossref_record: dict) -> dict[str, object]`: returns a stable per-seed result row.
- `analyze_reference_sets(openalex_works: list[dict], crossref_records: dict[str, dict]) -> pandas.DataFrame`.
- `reference_group_summary(rows: pandas.DataFrame) -> pandas.DataFrame`.

- [ ] **Step 1: Write fixture-driven tests for shared and exclusive DOI references, an empty Crossref list, a failed Crossref lookup, and references without DOI values. Assert the exact comparison group, counts, Jaccard, and RCR values. Include this metric assertion in `tests/test_references.py`:**

```python
def test_reference_set_metrics_use_shared_union_denominator():
    row = compare_seed_references(
        {"doi": "10.1000/seed", "referenced_dois": ["10.1000/a", "10.1000/b"]},
        {"status_code": 200, "message": {"reference": [{"DOI": "10.1000/a"}, {"DOI": "10.1000/c"}]}},
    )
    assert row["shared_reference_count"] == 1
    assert row["union_reference_count"] == 3
    assert row["jaccard_similarity"] == pytest.approx(1 / 3)
    assert row["rcr_openalex"] == pytest.approx(2 / 3)
    assert row["rcr_crossref"] == pytest.approx(2 / 3)
```
- [ ] **Step 2: Run `python -m pytest tests/test_references.py -q`; confirm the expected missing-module failure.**
- [ ] **Step 3: Implement the fixed groups `comparable_both_doi_sets_nonempty`, `crossref_200_reference_empty`, `crossref_200_reference_present_but_not_comparable`, and `crossref_404_or_request_failure`. Normalize DOI sets; calculate shared, observed-exclusive, union, Jaccard, and each source's RCR. Keep failures distinct from empty references. The core calculation is:**

```python
oa_set = {doi for value in openalex_work.get("referenced_dois", []) if (doi := normalize_doi(value))}
message = crossref_record.get("message", {})
cr_set = {doi for ref in message.get("reference", []) if (doi := normalize_doi(ref.get("DOI")))}
shared = oa_set & cr_set
union = oa_set | cr_set
jaccard = len(shared) / len(union) if union else None
rcr_openalex = len(oa_set) / len(union) if union else None
rcr_crossref = len(cr_set) / len(union) if union else None
```
- [ ] **Step 4: Run the test and assert that a pair with shared `{10.1000/a}`, OpenAlex `{10.1000/a, 10.1000/b}`, and Crossref `{10.1000/a, 10.1000/c}` has intersection 1, union 3, Jaccard 1/3, and both RCR values 2/3.**
- [ ] **Step 5: Commit with `git add src/refcompare/references.py tests/test_references.py tests/fixtures` and `git commit -m "feat: compare DOI reference sets"`.**

## Task 4: Build controlled networks and preserve citing-work snapshots

**Files:**
- Create: `src/refcompare/networks.py`
- Test: `tests/test_networks.py`
- Modify: `src/refcompare/api.py`

**Interfaces:**
- `build_graph_edges(seed_rows: pandas.DataFrame, openalex_by_doi: dict[str, dict], crossref_by_doi: dict[str, dict], citing_by_seed: dict[str, list[dict]]) -> dict[str, pandas.DataFrame]`: returns `Graph_OA`, `Graph_CR`, and `Graph_Shared` edge frames with `source_doi`, `target_doi`, and `edge_type` columns.
- `OpenAlexClient.fetch_citing_works(work: dict) -> list[dict]`: cursor-paginates `cites:<OpenAlex work id>` and returns every retrieved record for caching.

- [ ] **Step 1: Write a test with two seed works and synthetic citing records. Assert OpenAlex-only references appear only in `Graph_OA`, Crossref-only references only in `Graph_CR`, shared references in `Graph_Shared`, and identical citing edges are copied to all graphs. The edge fixture should use this shape:**

```python
seed_rows = pd.DataFrame([{"doi": "10.1000/seed", "comparison_group": "comparable_both_doi_sets_nonempty"}])
openalex_by_doi = {"10.1000/seed": {"referenced_dois": ["10.1000/a", "10.1000/shared"]}}
crossref_by_doi = {"10.1000/seed": {"message": {"reference": [{"DOI": "10.1000/b"}, {"DOI": "10.1000/shared"}]}}}
citing_by_seed = {"10.1000/seed": [{"doi": "10.1000/citing"}]}
```
- [ ] **Step 2: Run `python -m pytest tests/test_networks.py -q`; confirm failure before implementation.**
- [ ] **Step 3: Implement edge construction with normalized DOI nodes and self-edge rejection. Add cursor pagination with a maximum-page guard, `per-page=200`, and the same bounded retry helper. Write each seed's citing response to the run bundle before returning it. Build each row through this helper:**

```python
def add_edge(edges: set[tuple[str, str, str]], source: str, target: str, edge_type: str) -> None:
    source_doi = normalize_doi(source)
    target_doi = normalize_doi(target)
    if source_doi and target_doi and source_doi != target_doi:
        edges.add((source_doi, target_doi, edge_type))
```
- [ ] **Step 4: Rerun network tests and verify a fixture with no citing records produces valid empty edge frames with the documented columns.**
- [ ] **Step 5: Commit with `git add src/refcompare/api.py src/refcompare/networks.py tests/test_networks.py` and `git commit -m "feat: build controlled reference graphs"`.**

## Task 5: Implement ASP and ranking comparison metrics

**Files:**
- Create: `src/refcompare/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- `compute_asp(edges: pandas.DataFrame, nodes: list[str], damping: float = 0.85, tolerance: float = 1e-8, max_iter: int = 100) -> tuple[pandas.Series, dict[str, object]]`.
- `compare_rankings(scores: dict[str, pandas.Series], top_fraction: float = 0.10) -> tuple[pandas.DataFrame, pandas.DataFrame]`: returns graph-pair summary and per-object details for all three graph pairs.

- [ ] **Step 1: Write tests for a tiny directed graph with a known converged score order, empty graph handling, tied ranks, common-object filtering, top-10/top-20 clipping, top-decile overlap, and displacement summaries. Include these exact ASP checks in `tests/test_metrics.py`:**

```python
def test_asp_assigns_more_score_to_cited_node():
    edges = pd.DataFrame([{"source_doi": "10.1000/source", "target_doi": "10.1000/target"}])
    scores, status = compute_asp(edges, ["10.1000/source", "10.1000/target"])
    assert scores["10.1000/target"] > scores["10.1000/source"]
    assert status["converged"] is True


def test_rank_comparison_uses_only_common_objects():
    summary, details = compare_rankings({"Graph_OA": pd.Series({"a": 0.9, "b": 0.1}), "Graph_CR": pd.Series({"b": 0.8, "c": 0.2})})
    assert set(details["doi"]) == {"b"}
    assert summary.loc[0, "common_node_count"] == 1
```
- [ ] **Step 2: Run `python -m pytest tests/test_metrics.py -q`; confirm tests fail before implementation.**
- [ ] **Step 3: Implement sparse PageRank-style ASP with receiver rows/source columns, dangling-mass redistribution, normalization, convergence metadata, and paper defaults. Use this recurrence in `compute_asp`:**

```python
scores = np.full(len(node_ids), 1.0 / len(node_ids))
for iteration in range(1, max_iter + 1):
    updated = damping * (transition @ scores + scores[dangling].sum() / len(node_ids)) + (1.0 - damping) / len(node_ids)
    updated = np.asarray(updated).ravel()
    updated /= updated.sum()
    change = float(np.max(np.abs(updated - scores)))
    scores = updated
    if change < tolerance:
        break
```

Implement pairwise rank metrics on common scored objects only; report Kendall tau-b, Spearman rho, top-10/top-20 overlap and agreement, top-decile overlap, mean/median/P90 absolute displacement, and shares at thresholds 5 and 10. Use `scipy.stats.kendalltau(left, right, variant="b")` and `scipy.stats.spearmanr(left, right)`.
- [ ] **Step 4: Rerun metric tests; assert top-k is clipped to the common-object count and empty or one-object comparisons return finite results with explanatory status fields.**
- [ ] **Step 5: Commit with `git add src/refcompare/metrics.py tests/test_metrics.py` and `git commit -m "feat: compute ASP and ranking differences"`.**

## Task 6: Orchestrate online runs and deterministic offline reanalysis

**Files:**
- Create: `src/refcompare/pipeline.py`
- Modify: `src/refcompare/bundle.py`
- Test: `tests/test_pipeline.py`
- Create: `tests/fixtures/offline_run/manifest.json` and all small raw snapshots it references.

**Interfaces:**
- `run_online(dois: list[str], output_dir: Path, settings: ApiSettings, asp_settings: dict[str, object]) -> Path`: fetches seed/reference/citing data, writes a complete bundle, runs analysis, returns the manifest path.
- `run_offline(input_dir: Path, output_dir: Path | None = None, asp_overrides: dict[str, object] | None = None) -> Path`: validates a bundle, makes no network requests, recomputes derived outputs, returns the new manifest path.
- `analyze_snapshots(output_dir: Path, snapshots: dict[str, object], asp_settings: dict[str, object]) -> dict[str, Path]`: is the shared deterministic analysis operation used by both paths.

- [ ] **Step 1: Write a fixture-backed offline integration test that monkeypatches the API client to raise if called; assert all expected outputs are generated from saved snapshots alone. Add this test to `tests/test_pipeline.py`:**

```python
def test_offline_run_never_calls_api(tmp_path, monkeypatch, offline_bundle):
    def fail(*args, **kwargs):
        raise AssertionError("offline analysis attempted a network request")

    monkeypatch.setattr("refcompare.api.requests.Session.get", fail)
    manifest = run_offline(offline_bundle, output_dir=tmp_path / "rerun")
    assert manifest.exists()
    assert (tmp_path / "rerun" / "reference_metrics.csv").exists()
    assert (tmp_path / "rerun" / "summary.md").exists()
```
- [ ] **Step 2: Run `python -m pytest tests/test_pipeline.py -q`; confirm missing orchestrator behavior fails.**
- [ ] **Step 3: Implement the shared analysis path, online acquisition sequence, run-status transitions (`running`, `completed`, `partial`, `failed`), and offline bundle validation. Save raw OpenAlex seed/reference DOI responses, Crossref JSONL, and all citing-work pages. Record tool version, input counts, non-secret settings, source retrieval times, API statuses, and output paths. Preserve these orchestration signatures:**

```python
def run_online(dois: list[str], output_dir: Path, settings: ApiSettings, asp_settings: dict[str, object]) -> Path:
    bundle = create_run_bundle(output_dir, dois, asp_settings)
    snapshots = fetch_all_snapshots(dois, settings, bundle)
    outputs = analyze_snapshots(bundle, snapshots, asp_settings)
    return outputs["manifest"]


def run_offline(input_dir: Path, output_dir: Path | None = None, asp_overrides: dict[str, object] | None = None) -> Path:
    manifest = read_manifest(input_dir / "run_manifest.json")
    snapshots = load_snapshots(input_dir, manifest)
    destination = output_dir or input_dir / "reanalyzed"
    outputs = analyze_snapshots(destination, snapshots, {**manifest["asp_settings"], **(asp_overrides or {})})
    return outputs["manifest"]


def analyze_snapshots(output_dir: Path, snapshots: dict[str, object], asp_settings: dict[str, object]) -> dict[str, Path]:
    reference_rows = analyze_reference_sets(snapshots["openalex_works"], snapshots["crossref_records"])
    graph_edges = build_graph_edges(reference_rows, snapshots["openalex_by_doi"], snapshots["crossref_by_doi"], snapshots["citing_by_seed"])
    tables = calculate_all_metrics(reference_rows, graph_edges, asp_settings)
    return write_all_outputs(output_dir, snapshots["manifest"], tables)
```
- [ ] **Step 4: Run online-path tests using mocked API fixtures and offline tests with network access blocked; assert no secret appears anywhere under the fixture output directory.**
- [ ] **Step 5: Commit with `git add src/refcompare/pipeline.py src/refcompare/bundle.py tests/test_pipeline.py tests/fixtures/offline_run` and `git commit -m "feat: add reproducible online and offline pipelines"`.**

## Task 7: Export CSVs and plain-language Markdown report

**Files:**
- Create: `src/refcompare/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- `write_csv_outputs(tables: dict[str, pandas.DataFrame], output_dir: Path) -> list[Path]`: writes documented UTF-8-with-BOM CSVs and returns paths.
- `render_markdown_report(manifest: dict[str, object], tables: dict[str, pandas.DataFrame]) -> str`: returns a complete English report.
- `write_report(manifest: dict[str, object], tables: dict[str, pandas.DataFrame], output_dir: Path) -> Path`.

- [ ] **Step 1: Write tests using synthetic tables for a successful comparison, an incomplete API run, and zero comparable records. Assert the report explains Jaccard, RCR, Kendall tau-b, top-k overlap, and rank displacement in plain language; includes actual counts and values; states the DOI/API/one-hop limits; never claims universal database superiority; and never labels a missing source record as an empty reference list. Include this report contract:**

```python
def test_report_explains_metrics_and_limits(sample_manifest, sample_tables):
    report = render_markdown_report(sample_manifest, sample_tables)
    assert "Jaccard" in report and "shared references divided by the union" in report
    assert "Kendall tau-b" in report and "rank-order agreement" in report
    assert "submitted seed set" in report
    assert "does not establish that either database is universally superior" in report


def test_report_marks_api_failure_separately_from_empty_references(incomplete_tables):
    report = render_markdown_report({}, incomplete_tables)
    assert "request failed" in report
    assert "empty reference list" not in report
```
- [ ] **Step 2: Run `python -m pytest tests/test_report.py -q`; confirm the tests fail before implementation.**
- [ ] **Step 3: Implement stable output names: `reference_metrics.csv`, `reference_groups.csv`, `graph_statistics.csv`, `asp_scores.csv`, `ranking_agreement.csv`, `ranking_details.csv`, and `summary.md`. Generate observations only from supplied metrics, label them as results for the submitted set, and distinguish missing/incomplete data. Build the report using this deterministic structure:**

```python
sections = [
    "# RefCompare results",
    render_sample_and_retrieval_counts(manifest, tables),
    render_reference_metrics(tables["reference_metrics"]),
    render_ranking_metrics(tables["ranking_agreement"]),
    render_metric_definitions(),
    render_limitations(),
]
return "\n\n".join(section for section in sections if section)
```
- [ ] **Step 4: Rerun report tests and inspect the generated fixture report for readable headings, a concise interpretation, metric definitions, and method limitations.**
- [ ] **Step 5: Commit with `git add src/refcompare/report.py tests/test_report.py` and `git commit -m "feat: export tables and interpreted report"`.**

## Task 8: Finish CLI, docs, examples, license, and CI

**Files:**
- Create: `src/refcompare/cli.py`
- Create: `tests/test_cli.py`
- Create: `README.md`, `README.zh-CN.md`, `examples/seed_dois.txt`, `LICENSE`, `.github/workflows/tests.yml`
- Modify: `pyproject.toml`

**Interfaces:**
- `main(argv: list[str] | None = None) -> int`: supports `run --dois PATH --output PATH [--mailto EMAIL] [--openalex-api-key KEY]` and `analyze --input-dir PATH [--output PATH] [--damping FLOAT] [--tolerance FLOAT] [--max-iter INT] [--top-fraction FLOAT]`.
- `refcompare --help` and each subcommand's `--help` explain required files, credentials, outputs, and offline behavior.

- [ ] **Step 1: Write CLI tests for help, invalid DOI files, missing Crossref email, valid mocked online run, and offline analyze. Assert nonzero exit codes and plain actionable messages for invalid configuration, and a zero exit code for completed fixture runs. Include these cases in `tests/test_cli.py`:**

```python
from refcompare.cli import main


def test_help_returns_zero(capsys):
    assert main(["--help"]) == 0
    assert "run" in capsys.readouterr().out


def test_run_requires_crossref_email(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    path = tmp_path / "dois.txt"
    path.write_text("10.1234/example\n", encoding="utf-8")
    assert main(["run", "--dois", str(path), "--output", str(tmp_path / "out")]) == 2
    assert "Crossref email" in capsys.readouterr().err
```
- [ ] **Step 2: Run `python -m pytest tests/test_cli.py -q`; confirm command entry point and behavior are missing.**
- [ ] **Step 3: Implement `argparse` subcommands, environment-variable support (`CROSSREF_MAILTO`, `OPENALEX_API_KEY`), explicit CLI overrides, DOI summary before network access, per-seed progress, clear final output paths, and error handling that returns nonzero status without exposing credentials. Use this parser shape:**

```python
parser = argparse.ArgumentParser(prog="refcompare")
subparsers = parser.add_subparsers(dest="command", required=True)
run = subparsers.add_parser("run", help="fetch API data and analyze a DOI list")
run.add_argument("--dois", type=Path, required=True)
run.add_argument("--output", type=Path, required=True)
run.add_argument("--mailto", default=os.getenv("CROSSREF_MAILTO"))
run.add_argument("--openalex-api-key", default=os.getenv("OPENALEX_API_KEY"))
analyze = subparsers.add_parser("analyze", help="reanalyze a saved run without network access")
analyze.add_argument("--input-dir", type=Path, required=True)
analyze.add_argument("--output", type=Path)
```
- [ ] **Step 4: Write both READMEs with copy-paste install/run/offline commands, DOI input rules, API setup, output explanations, interpretation guide, limitations, troubleshooting, and citation instructions. Add a synthetic example DOI list and full MIT license text.**
- [ ] **Step 5: Configure GitHub Actions to run `python -m pytest -q` on Ubuntu for Python 3.10, 3.12, 3.14 and Windows for Python 3.12, with no secrets or network calls. Use this workflow matrix:**

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            python: "3.10"
          - os: ubuntu-latest
            python: "3.12"
          - os: ubuntu-latest
            python: "3.14"
          - os: windows-latest
            python: "3.12"
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install -e . pytest
      - run: python -m pytest -q
```

Run the entire suite locally and verify a clean install with `python -m pip install -e .`.
- [ ] **Step 6: Commit with `git add pyproject.toml src/refcompare/cli.py tests/test_cli.py README.md README.zh-CN.md examples/seed_dois.txt LICENSE .github/workflows/tests.yml` and `git commit -m "docs: prepare RefCompare for public use"`.**

## Task 9: Verify repository contents and publish the public GitHub repository

**Files:**
- Review: all tracked files, test results, README installation commands, `.gitignore`, and GitHub Actions result.

- [ ] **Step 1: Run `python -m pytest -q` and `python -m pip install -e .`; verify all tests pass and the `refcompare --help` command works in a fresh shell.**
- [ ] **Step 2: Search tracked files for email addresses, API key patterns, manuscript names, corpus directories, and local run-result paths; remove any private or generated material.**
- [ ] **Step 3: Review `git status --short`, confirm only intended source, tests, docs, synthetic examples, license, and workflow files are tracked, then commit any final fixes.**
- [ ] **Step 4: Create public GitHub repository `RefCompare` under the authenticated user's account, add it as `origin`, push `main`, and verify the repository URL, default branch, README rendering, and green CI run.**
- [ ] **Step 5: Report the public repository URL, install and example commands, validation result, and any GitHub account limitation if repository creation is unavailable.**

## Self-review coverage map

- DOI and API input requirements: Tasks 1-2 and 8.
- Complete online bundle and network-free offline analysis: Tasks 2 and 6.
- Reference metrics and separate source failure states: Task 3.
- Controlled graphs and paper ASP/ranking metrics: Tasks 4-5.
- CSV outputs and bounded, sample-specific plain-language interpretation: Task 7.
- Windows/Linux, supported Python, no-secret CI and user documentation: Task 8.
- Public MIT GitHub repository and private-data exclusion: Task 9.
