# Release reproduction validation

RefCompare 0.1.1, Python 3.14, numpy 2.3.5, pandas 3.0.1, scipy 1.18.1, requests 2.34.2. All 36 synthetic regression tests pass under pytest 8.4.2.

The frozen research archive reproduces five primary discipline analyses (10,000 sampled seeds) and all 30 paired OpenAlex/OpenCitations network variants. Verification made no API requests. All 517 checks passed: DOI membership/classification, reference metrics, typed primary edges, full-graph ASP scores, correlations/displacements, deterministic fixed and expanded cutoffs, and all stored numerical 2 x 3 result columns. All 30 robustness networks converged.

Historical exports are retained unchanged. Some historical fixed cutoffs used arbitrary ordering at tied scores. The release follows the manuscript rule (score descending, DOI ascending); fixed/expanded benchmarks are independently reconstructed from the original saved scores. Differences are explicitly recorded in historical_cutoff_differences.csv. No scoring parameters or historical ASP scores were changed.

Evidence: checks.csv and summary.json. The released archive contains the portable inputs, results and verification scripts; download it from the v0.1.1 release and follow its README to reproduce and validate independently.
