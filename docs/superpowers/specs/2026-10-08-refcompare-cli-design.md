# RefCompare Command-Line Tool Design

Date: 2026-10-08

## Purpose

RefCompare will turn the research workflow comparing OpenAlex and Crossref reference data into a small, reusable command-line tool. Researchers should be able to follow a short quick start, run a DOI list, inspect transparent per-record data, and understand what the generated comparisons mean without needing to read the implementation.

The first release targets batches of up to a few dozen seed works. A seed DOI identifies a work whose references are compared. Ranking-impact analysis then evaluates the cited works represented by those reference sets, using the paper's controlled one-hop network method.

## Goals

- Accept a plain-text DOI list, one DOI per line, and retrieve required records from OpenAlex and Crossref.
- Reanalyze a saved RefCompare run bundle without making network requests.
- Reproduce the paper's reference-set and ASP ranking-impact workflow with paper-method defaults, while allowing advanced users to override ranking parameters.
- Export machine-readable CSV files and a plain-language Markdown report that explains the sample, metrics, observations, and limitations.
- Package the workflow as an installable Python CLI in a clean, public GitHub repository named `RefCompare`, under the MIT License.
- Keep the tool approachable through validated commands, useful progress messages, clear errors, an English-first README with a Chinese guide, and a small example input.

## Non-goals for the first release

- A graphical interface, hosted web service, or account system.
- Arbitrary OpenAlex/Crossref export formats. Offline analysis accepts the standard run bundle written by RefCompare.
- Claims that one bibliographic database is universally better. Generated interpretations apply only to the submitted seed set, retrieved records, and documented method.
- Very large population sampling as the primary user path. The first release is designed around user-supplied DOI lists and modest batches.

## User workflows

### Online run

The user installs the package, supplies one DOI per line, supplies their own Crossref contact email, and optionally configures an OpenAlex API key. The CLI validates the file and options before contacting APIs, displays progress, applies bounded retries and rate limits, then writes a complete run directory.

Illustrative interface:

```text
refcompare run --dois seed_dois.txt --mailto researcher@example.org --output results/my_run
```

The Crossref email is provided by the user at run time or through an environment variable. An OpenAlex key is optional and is also supplied at run time or through an environment variable. Neither value is written to run manifests, logs, or checked-in files.

### Offline analysis

A user points the CLI at the complete data bundle created by a previous RefCompare online run. The tool uses only the saved snapshots and recomputes derived tables and report text, so the analysis can be repeated without API access.

Illustrative interface:

```text
refcompare analyze --input-dir results/my_run
```

The run bundle contains the normalized seed list, source snapshots needed for analysis (including fetched citing-work records), the run manifest, and generated outputs. This gives the offline path enough information to reproduce the analysis without silently using fresh API data.

## Analysis workflow and definitions

1. Normalize DOI values and retain a clear accounting of valid, duplicate, and invalid input rows.
2. Retrieve each seed work from OpenAlex and its Crossref work record. Resolve OpenAlex referenced-work identifiers to DOIs where possible.
3. Compare normalized DOI reference sets for each seed. Record shared, OpenAlex-observed-exclusive, Crossref-observed-exclusive, union counts, Jaccard similarity, and the paper's reference coverage ratios. Preserve separate states for missing records, empty reference fields, and records without DOI-comparable references.
4. Build three controlled graph variants: OpenAlex reference edges, Crossref reference edges, and shared reference edges. Use the same OpenAlex citing-work edges in each variant, matching the paper's design.
5. Compute ASP scores for the cited works and compare graph-pair rankings on their common scored objects. Report Kendall tau-b, Spearman rho, top-10 and top-20 overlap/agreement, and absolute rank-displacement mean, median, 90th percentile, and threshold shares, using the paper's definitions.
6. Produce record-level CSVs, aggregate summaries, and a Markdown report. The report states the submitted sample size and API coverage, explains what each metric measures, describes the observed result in context, and names the DOI-resolution, API-snapshot, and one-hop-network limitations. It avoids general claims about database quality.

For a seed with OpenAlex DOI reference set `R_OA` and Crossref DOI reference set `R_CR`, the report uses `Jaccard = |R_OA ∩ R_CR| / |R_OA ∪ R_CR|` and each source's reference coverage ratio `RCR_source = |R_source| / |R_OA ∪ R_CR|`. These are DOI-resolved diagnostics over the observed union, not estimates of complete reference-list recall.

ASP defaults follow the paper implementation: damping `0.85`, convergence tolerance `1e-8`, and maximum `100` iterations. Rank comparisons use descending ASP ranks on each pair's common scored objects, minimum-rank tie handling, Kendall tau-b, Spearman rho, absolute top-10/top-20 overlap and agreement, top-decile overlap, and rank-displacement mean, median, P90, and shares at displacement thresholds 5 and 10. Advanced options may override ASP settings and the top-decile fraction; every override is recorded in the run manifest and disclosed in the report. ASP is described as a local score within the constructed one-hop network, not an absolute measure of scholarly prestige.

## Package structure

The installable package will use a `src` layout and a `pyproject.toml` entry point. Responsibilities are separated into:

- input validation and DOI normalization;
- OpenAlex and Crossref clients, retries, rate limiting, and raw snapshot storage;
- reference-set analysis;
- graph construction and ASP scoring;
- rank-comparison metrics;
- CSV, manifest, and Markdown report generation;
- CLI argument parsing and user-facing progress/errors.

The command line will use Python's standard `argparse` interface to keep installation light. The supported runtime will be Python 3.10 or newer. Dependencies will be limited to those required by the existing algorithms and outputs, with compatible versions declared in package metadata.

## Outputs

A successful run directory will include:

- a JSON manifest containing tool version, run time, input counts, non-secret options, API retrieval counts, source snapshot timestamps, and output paths;
- raw OpenAlex, Crossref, and citing-work snapshots sufficient for offline reanalysis;
- CSV files for per-seed reference-set metrics and quality groups;
- aggregate CSV summaries for reference-quality groups and graph-level ranking comparisons;
- CSV files for graph statistics, ASP scores, and per-object ranking details;
- an English Markdown summary with a concise plain-language interpretation and method limitations.

CSV files will use stable, documented column names and UTF-8 encoding. The example data will be synthetic or otherwise clearly licensed for redistribution and will not contain credentials or private research material.

## Error handling and data handling

- Validate DOI input, paths, email configuration, and API response shapes before analysis.
- Retry transient network failures and rate limits with bounded backoff; never retry indefinitely.
- Distinguish not-found, empty-reference, invalid/non-comparable, rate-limited, and request-failure cases in outputs.
- Preserve per-record failures and mark incomplete runs in the manifest. Do not silently treat missing API data as an empty reference set.
- Exclude email addresses, API keys, and authorization data from manifests and logs.
- Keep the manuscript, research corpus, local result archives, and user credentials outside the public repository.

## Testing and release

Unit tests will cover DOI normalization, set metrics, source-state classification, ASP behavior, rank metrics, manifest privacy, and report interpretation rules. Fixture-backed integration tests will exercise both online-style processing and full offline reanalysis without live API calls. GitHub Actions will test Python 3.10, 3.12, and 3.14 on Linux, plus a Windows run on Python 3.12.

The repository will include an English-first README with a Chinese quick-start guide, installation and usage examples, input/output definitions, API setup, limitations, a MIT license, and instructions for citing the software. The first release will be published as a public GitHub repository. Package publication to PyPI and deployment of any hosted service are outside the initial scope.

## Acceptance criteria

- A new user can install the package and run a small DOI text file by following the quick start.
- A run produces a complete reusable bundle, detailed CSV outputs, a summary CSV, and a readable Markdown explanation.
- Running offline analysis against a saved bundle reproduces derived outputs without network access.
- API failures and non-comparable records are visible and described rather than silently discarded.
- Tests pass without live credentials or live API calls.
- The public repository contains no manuscript, research corpus, private raw results, or credentials.
