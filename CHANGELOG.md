# Changelog

## 0.1.1 — 2026-10-11

- Default graphs use clean-comparable seeds; pairwise rankings use common referenced works after scoring full one-hop graphs.
- Expose graph and ranking scopes in the CLI, run manifest, CSVs, and report. Keep broader 0.1.0 scopes as explicit options.
- Match the study's operational normalization for retrieved reference and citing DOIs, retaining strict validation for user-supplied seeds.
- Preserve successful-reference-field checks and distinguish retrieval failures from empty reference lists.
- Make fixed Top-k selection deterministic: score descending, DOI ascending. Add cutoff-expanded set sizes, intersection, union, Jaccard, and normalized mean rank displacement.
- Save reusable offline reanalysis bundles and add original-study parity and portable reproduction verification scripts.
- Release a frozen DOI research-data and reproduction archive covering primary and paired OpenAlex/OpenCitations 2×3 analyses.
