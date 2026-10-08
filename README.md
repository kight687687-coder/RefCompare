# RefCompare

RefCompare is a command-line research tool for comparing DOI-resolved reference lists retrieved from OpenAlex and Crossref, then assessing how the observed reference differences affect local rankings in controlled one-hop citation networks.

It is designed for small user-supplied batches (typically a few dozen seed works). Each seed DOI identifies a work whose reference list is compared. RefCompare keeps the API snapshots, reports incomplete records clearly, and explains the results in a Markdown summary.

## Install

Requires Python 3.10 or newer.

```bash
git clone <repository-url-shown-on-this-page>
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

- **Jaccard similarity** is the number of DOI references shared by OpenAlex and Crossref divided by the union of DOI references observed in either source. Higher values mean more overlap in the observed sets.
- **Reference coverage ratio (RCR)** is a source's DOI-reference count divided by that same observed union. It is an observed-set diagnostic, not a measure of all references in the work.
- **ASP** is a PageRank-style local score over each constructed one-hop network. It is not an absolute measure of scholarly prestige.
- **Kendall tau-b** and **Spearman rho** summarize rank-order agreement for works scored in both networks.
- **Top-k overlap** counts how many works occur in both highest-scoring groups. Rank displacement reports how many places common works move.

The report describes only the submitted seed set and the API snapshots retrieved for that run. DOI matching can miss references without a DOI or with unresolved identifiers. API records change over time. The controlled ranking analysis uses a one-hop network and keeps retrieved citing-work edges fixed across graph variants. Results do not establish that either source is universally superior.

## Outputs

- `run_manifest.json`: run status, timestamps, settings, API counts, and output paths. It contains no email address or API key.
- `raw/`: OpenAlex, Crossref, and citing-work snapshots used for offline reanalysis.
- `reference_metrics.csv`: one row per seed, including comparison group, set sizes, overlap, Jaccard, and RCR.
- `reference_groups.csv`: count and share for each retrieval/comparability state.
- `graph_statistics.csv`: node and edge counts for OpenAlex, Crossref, and shared-reference graphs.
- `asp_scores.csv`: ASP score and convergence details per graph and DOI.
- `ranking_agreement.csv`: pairwise rank agreement, top-10/top-20 and top-fraction overlap, and displacement summaries.
- `ranking_details.csv`: pairwise scores, ranks, top-k membership, and absolute displacement for every common work.
- `summary.md`: a plain-language interpretation and limitations.

## Parameters

The defaults reproduce the paper's method: ASP damping `0.85`, tolerance `1e-8`, maximum `100` iterations, and top fraction `0.10`. Advanced users can override them:

```bash
refcompare run --dois seed_dois.txt --output results/custom \
  --mailto you@example.org --damping 0.85 --tolerance 1e-8 --max-iter 100 --top-fraction 0.10
```

Overrides are recorded in the run manifest. Online retrieval may take time because the tool requests references and citing works; API coverage and failures are shown in the outputs.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

The tests use synthetic fixtures and do not need API credentials or network access.

## Citation

Please cite the RefCompare repository version used and the accompanying paper. Once a release has a DOI, use the archived software DOI as well.

## License

MIT. See [LICENSE](LICENSE).

## 中文快速说明

中文安装和运行说明见 [README.zh-CN.md](README.zh-CN.md)。
