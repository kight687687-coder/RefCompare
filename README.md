# RefCompare

RefCompare is a command-line research tool for comparing DOI-resolved reference lists retrieved from OpenAlex and Crossref, then assessing how the observed reference differences affect local rankings in controlled one-hop citation networks.

It is designed for small user-supplied batches (typically a few dozen seed works). Each seed DOI identifies a work whose reference list is compared. RefCompare keeps the API snapshots, reports incomplete records clearly, and explains the results in a Markdown summary.

## Install

Requires Python 3.10 or newer.

```bash
git clone --branch v0.1.1 https://github.com/kight687687-coder/RefCompare.git
cd RefCompare
python -m pip install .
refcompare --help
```

If the `refcompare` command is not on your shell's `PATH`, use `python -m refcompare --help` (and `python -m refcompare run ...`).

For local development, install with `python -m pip install -e ".[dev]"`.

## Quick start

Create `seed_dois.txt` with one DOI per line. DOI URLs and `doi:` prefixes are accepted. Blank lines and lines beginning with `#` are ignored.

Set your own Crossref contact email, then run:

```bash
# macOS/Linux
export CROSSREF_MAILTO="you@example.org"
refcompare run --dois seed_dois.txt --output results/my_run
```

```powershell
# Windows PowerShell
$env:CROSSREF_MAILTO = "you@example.org"
refcompare run --dois seed_dois.txt --output results/my_run
```

You can instead pass `--mailto you@example.org`. An OpenAlex API key is optional; set `OPENALEX_API_KEY` or pass `--openalex-api-key`. Credentials are used only for requests and are excluded from manifests and logs.

When the command completes, open `results/my_run/summary.md`. The directory also contains a reusable set of raw API snapshots and detailed CSV files.

## Reanalyze offline

The saved run bundle contains the API snapshots required to recompute the results without contacting OpenAlex or Crossref:

```bash
refcompare analyze --input-dir results/my_run
```

By default, reanalysis outputs go into `results/my_run/reanalyzed`. You can choose another destination with `--output`.

## What the report means

The default method constructs networks only from **clean-comparable seeds**: both API records must be successfully retrieved, OpenAlex must expose a reference field, and both sources must have nonempty valid DOI-reference sets. All submitted records remain in the reference diagnostics. ASP is computed on each full one-hop graph, including seed, reference, and citing nodes. Ranking comparisons then use only **pairwise common referenced works**, identified by reference-edge targets in both graphs. A seed or citing DOI qualifies only if it also has this reference role in both graphs. Empty eligible sets produce no ranking comparison; the tool never automatically broadens the scope.

Retrieved reference and citing identifiers use the study's operational normalization: lowercase, remove DOI URL/`doi:` prefixes and trailing punctuation, then require `10.` and `/`. This retains some malformed identifiers present in the original snapshots and does not validate DOI registration. User-supplied seed input uses the stricter DOI format check. This distinction is necessary for reproducing the published study tables from the same snapshots.

- **Jaccard similarity** is the number of DOI references shared by OpenAlex and Crossref divided by the union of DOI references observed in either source. Higher values mean more overlap in the observed sets.
- **Reference coverage ratio (RCR)** is a source's DOI-reference count divided by that same observed union. It is an observed-set diagnostic, not a measure of all references in the work.
- **ASP** is a PageRank-style local score over each constructed one-hop network. It is not an absolute measure of scholarly prestige.
- **Kendall tau-b** and **Spearman rho** summarize rank-order agreement for eligible referenced works scored in both networks.
- **Top-k overlap** counts how many works occur in both highest-scoring groups. Fixed groups use score descending and DOI ascending at tied cutoffs. Tie-expanded diagnostics include every work at or above the cutoff score and report sizes and Jaccard similarity. Rank displacement uses minimum ranks for ties and reports how many places common works move.

The report describes only the submitted seed set and the API snapshots retrieved for that run. DOI matching can miss references without a DOI or with unresolved identifiers. API records change over time. The controlled ranking analysis uses a one-hop network and keeps retrieved citing-work edges fixed across graph variants. Results do not establish that either source is universally superior.

## Outputs

- `run_manifest.json`: run status, timestamps, settings, API counts, and output paths. It contains no email address or API key.
- `raw/`: OpenAlex, Crossref, and citing-work snapshots used for offline reanalysis.
- `reference_metrics.csv`: one row per seed, including comparison group, set sizes, overlap, Jaccard, and RCR.
- `reference_groups.csv`: count and share for each retrieval/comparability state.
- `analysis_scope.csv`: actual graph and ranking scopes, submitted, clean-comparable, and network seed counts.
- `graph_statistics.csv`: node and edge counts for OpenAlex, Crossref, and shared-reference graphs.
- `asp_scores.csv`: ASP score and convergence details per graph and DOI.
- `ranking_agreement.csv`: pairwise rank agreement, top-10/top-20 and top-fraction overlap, and displacement summaries.
- `ranking_details.csv`: pairwise scores, ranks, top-k membership, and absolute displacement for every eligible common work, with the actual scopes recorded.
- `summary.md`: a plain-language interpretation and limitations.

## Parameters

The defaults implement the paper's analysis scope: `--graph-scope clean-comparable` and `--ranking-scope common-references`, with ASP damping `0.85`, tolerance `1e-8`, maximum `100` iterations, and top fraction `0.10`. Advanced users can override them:

```bash
refcompare run --dois seed_dois.txt --output results/custom \
  --mailto you@example.org --damping 0.85 --tolerance 1e-8 --max-iter 100 --top-fraction 0.10
```

Overrides are recorded in the run manifest. Online retrieval may take time because the tool requests references and citing works; API coverage and failures are shown in the outputs.

To explicitly request the broader population used by version 0.1.0:

```bash
refcompare analyze --input-dir results/my_run \
  --graph-scope all-records --ranking-scope all-common-nodes
```

Both options are available on `run` and `analyze` and may be selected independently. Offline analysis inherits saved scope settings unless overridden; bundles without scope settings use the paper defaults. Reanalysis outputs include snapshots and can themselves be reanalyzed. These alternative scopes are additional diagnostics and differ from the paper's primary analysis.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

The tests use synthetic fixtures and do not need API credentials or network access.

Version 0.1.1 is the method-aligned release. Its fixed code snapshot and research data are available from the [v0.1.1 release](https://github.com/kight687687-coder/RefCompare/releases/tag/v0.1.1). Matching requires the same snapshots, DOI normalization, graph construction, ASP settings, comparison objects, and tie handling. For a local original study checkout, `python scripts/verify_paper_parity.py --study-root PATH --output OUTPUT_DIR` checks against saved inputs and scores. Historical result exports used arbitrary row order at some tied cutoffs; this verifier independently reconstructs fixed cutoffs using the manuscript's DOI rule and leaves historical files unchanged.

## Frozen research data and reproduction

Download [RefCompare_research_data_20261011.zip](https://github.com/kight687687-coder/RefCompare/releases/download/v0.1.1/RefCompare_research_data_20261011.zip), extract it, and follow its README. The archive includes minimized DOI-level source snapshots for all 10,000 sampled works, fixed sample membership, primary and paired 2×3 graph/ranking data, retrieval evidence, illustration source data, frozen software, exact dependency versions, and SHA-256 checksums.

From the extracted archive directory (Python 3.14 is the validated environment):

```bash
python -m pip install -r requirements.txt
python reproduce_primary.py
python robustness_final.py
python verify_reproduction.py --output reproduction_validation
```

Both analyses run offline after dependencies are installed. Primary defaults use each graph pair's common reference targets; the study-specific robustness driver uses one fixed shared-edge target universe across all six variants within a discipline. The archive preserves sufficient DOI-level inputs for reanalysis rather than every original bibliographic API field. It does not require live API credentials. Historical exports are retained for provenance alongside recomputed results and an explicit cutoff-difference report.

## Citation

Please cite the RefCompare repository version used and the accompanying paper. Once a release has a DOI, use the archived software DOI as well.

## License

MIT. See [LICENSE](LICENSE).

## 中文快速说明

中文安装和运行说明见 [README.zh-CN.md](README.zh-CN.md)。
