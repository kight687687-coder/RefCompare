"""ASP scoring and pairwise ranking-impact metrics."""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.sparse import csc_matrix, diags
from scipy.stats import kendalltau, spearmanr


def compute_asp(
    edges: pd.DataFrame,
    nodes: Iterable[str],
    damping: float = 0.85,
    tolerance: float = 1e-8,
    max_iter: int = 100,
) -> tuple[pd.Series, dict[str, object]]:
    """Compute local PageRank-style ASP scores on a directed citation graph."""
    if not 0 <= damping < 1:
        raise ValueError("damping must be in [0, 1)")
    if tolerance <= 0 or max_iter <= 0:
        raise ValueError("tolerance and max_iter must be positive")
    node_ids = sorted(set(nodes))
    n = len(node_ids)
    if n == 0:
        return pd.Series(dtype=float, name="asp"), {"iterations": 0, "converged": True, "max_change": 0.0}
    index = {doi: i for i, doi in enumerate(node_ids)}
    rows: list[int] = []
    cols: list[int] = []
    if not edges.empty:
        for row in edges.itertuples(index=False):
            source = getattr(row, "source_doi")
            target = getattr(row, "target_doi")
            if source in index and target in index:
                # A source cites a target: the target receives prestige from the source.
                rows.append(index[target])
                cols.append(index[source])
    adjacency = csc_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n), dtype=float)
    out_degree = np.asarray(adjacency.sum(axis=0)).ravel()
    dangling = out_degree == 0
    safe_degree = out_degree.copy()
    safe_degree[dangling] = 1.0
    transition = adjacency @ diags(1.0 / safe_degree, format="csc")
    scores = np.full(n, 1.0 / n)
    converged = False
    max_change = float("inf")
    iteration = 0
    for iteration in range(1, max_iter + 1):
        updated = damping * (transition @ scores + scores[dangling].sum() / n) + (1.0 - damping) / n
        updated = np.asarray(updated).ravel()
        updated /= updated.sum()
        max_change = float(np.max(np.abs(updated - scores)))
        scores = updated
        if max_change < tolerance:
            converged = True
            break
    return pd.Series(scores, index=node_ids, name="asp"), {
        "iterations": iteration,
        "converged": converged,
        "max_change": max_change,
    }


def _rank_displacement(left_rank: pd.Series, right_rank: pd.Series) -> dict[str, float]:
    displacement = (left_rank - right_rank).abs().dropna()
    if displacement.empty:
        return {
            "rank_displacement_mean": 0.0,
            "rank_displacement_median": 0.0,
            "rank_displacement_p90": 0.0,
            "rank_displacement_ge_5_rate": 0.0,
            "rank_displacement_ge_10_rate": 0.0,
        }
    return {
        "rank_displacement_mean": float(displacement.mean()),
        "rank_displacement_median": float(displacement.median()),
        "rank_displacement_p90": float(displacement.quantile(0.90)),
        "rank_displacement_ge_5_rate": float((displacement >= 5).mean()),
        "rank_displacement_ge_10_rate": float((displacement >= 10).mean()),
    }


def _safe_stat(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def compare_rankings(
    scores: dict[str, pd.Series], top_fraction: float = 0.10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare every graph pair using only objects scored in both graphs."""
    if not 0 < top_fraction <= 1:
        raise ValueError("top_fraction must be in (0, 1]")
    summaries: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []
    for left_name, right_name in combinations(scores, 2):
        common = scores[left_name].index.intersection(scores[right_name].index)
        left = scores[left_name].loc[common].astype(float)
        right = scores[right_name].loc[common].astype(float)
        n = len(common)
        left_rank = left.rank(ascending=False, method="min")
        right_rank = right.rank(ascending=False, method="min")
        top_n = min(n, max(1, int(n * top_fraction))) if n else 0
        left_top = set(left.sort_values(ascending=False).head(top_n).index)
        right_top = set(right.sort_values(ascending=False).head(top_n).index)
        overlap = len(left_top & right_top)
        top10_n = min(n, 10)
        top20_n = min(n, 20)
        left_top10 = set(left.sort_values(ascending=False).head(top10_n).index)
        right_top10 = set(right.sort_values(ascending=False).head(top10_n).index)
        left_top20 = set(left.sort_values(ascending=False).head(top20_n).index)
        right_top20 = set(right.sort_values(ascending=False).head(top20_n).index)
        top10_overlap = len(left_top10 & right_top10)
        top20_overlap = len(left_top20 & right_top20)
        if n >= 2:
            tau = kendalltau(left, right, variant="b")
            rho = spearmanr(left, right)
            tau_value, tau_p = _safe_stat(tau.statistic), _safe_stat(tau.pvalue)
            rho_value, rho_p = _safe_stat(rho.statistic), _safe_stat(rho.pvalue)
        else:
            tau_value = tau_p = rho_value = rho_p = None
        displacement = _rank_displacement(left_rank, right_rank)
        summaries.append({
            "left_graph": left_name,
            "right_graph": right_name,
            "common_node_count": n,
            "kendall_tau_b": tau_value,
            "kendall_pvalue": tau_p,
            "spearman_rho": rho_value,
            "spearman_pvalue": rho_p,
            "top_fraction": top_fraction,
            "top_fraction_n": top_n,
            "top_fraction_overlap_count": overlap,
            "top_fraction_overlap_rate": overlap / top_n if top_n else 0.0,
            "top10_n": top10_n,
            "top10_overlap_count": top10_overlap,
            "top10_agreement_rate": top10_overlap / top10_n if top10_n else 0.0,
            "top20_n": top20_n,
            "top20_overlap_count": top20_overlap,
            "top20_agreement_rate": top20_overlap / top20_n if top20_n else 0.0,
            **displacement,
        })
        for doi in common:
            detail_rows.append({
                "doi": doi,
                "left_graph": left_name,
                "right_graph": right_name,
                f"{left_name}_asp": float(left.loc[doi]),
                f"{right_name}_asp": float(right.loc[doi]),
                f"{left_name}_rank": float(left_rank.loc[doi]),
                f"{right_name}_rank": float(right_rank.loc[doi]),
                "rank_change_abs": float(abs(left_rank.loc[doi] - right_rank.loc[doi])),
                "left_top10": doi in set(left.sort_values(ascending=False).head(min(10, n)).index),
                "right_top10": doi in set(right.sort_values(ascending=False).head(min(10, n)).index),
                "left_top20": doi in set(left.sort_values(ascending=False).head(min(20, n)).index),
                "right_top20": doi in set(right.sort_values(ascending=False).head(min(20, n)).index),
            })
    return pd.DataFrame(summaries), pd.DataFrame(detail_rows)
