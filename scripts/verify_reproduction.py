"""Validate portable reproduction against frozen historical inputs and outputs."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd

DISCIPLINES = ("computer_science", "medicine", "history", "physics", "economics")
GRAPH_MAP = dict(zip(("Graph_OA", "Graph_CR", "Graph_Shared"), ("graph_openalex", "graph_crossref", "graph_shared")))


def read(path):
    return pd.read_csv(path, float_precision="round_trip")


def validate(package, recomputed, output):
    checks, corrections = [], []
    def check(name, passed, **details):
        checks.append({"check": name, "passed": bool(passed), **details})
    for discipline in DISCIPLINES:
        generated = recomputed / "primary" / discipline
        original = package / "historical_primary" / discipline
        expected = read(package / "primary_inputs" / discipline / "original_reference_metrics.csv").set_index("doi").sort_index()
        actual = read(generated / "reference_metrics.csv").set_index("doi").sort_index()
        check(f"{discipline}:submitted_dois", actual.index.equals(expected.index))
        check(f"{discipline}:comparison_groups", actual.comparison_group.equals(expected.comparison_group))
        for column in ("openalex_doi_reference_count", "crossref_raw_reference_count", "crossref_doi_reference_count", "shared_reference_count", "union_reference_count", "rcr_openalex", "rcr_crossref", "jaccard_similarity"):
            if column in expected:
                check(f"{discipline}:reference:{column}", np.allclose(actual[column], expected[column], equal_nan=True, rtol=1e-12, atol=1e-12))
        eligible = {}
        for graph in GRAPH_MAP:
            old_edges, edges = read(original / f"{graph}_edges.csv"), read(generated / f"{graph}_edges.csv")
            check(f"{discipline}:{graph}:typed_edges", set(old_edges.itertuples(index=False,name=None)) == set(edges.itertuples(index=False,name=None)))
            old_scores = read(original / f"{graph}_scores.csv").set_index("doi").asp.sort_index()
            scores = read(generated / "asp_scores.csv").query("graph == @graph").set_index("doi").asp_score.sort_index()
            same_nodes = scores.index.equals(old_scores.index)
            check(f"{discipline}:{graph}:score_nodes", same_nodes)
            check(f"{discipline}:{graph}:scores", same_nodes and np.allclose(scores,old_scores,rtol=1e-10,atol=1e-14), max_abs_error=float((scores-old_scores).abs().max()))
            refs = set(old_edges.loc[old_edges.edge_type.isin(["reference","shared_reference","参考文献"]),"target_doi"])
            eligible[graph] = old_scores.loc[old_scores.index.isin(refs)]
        rank = read(generated / "ranking_agreement.csv").set_index(["left_graph","right_graph"])
        for row in read(original / "ranking_agreement.csv").to_dict("records"):
            inverse = {v:k for k,v in GRAPH_MAP.items()}
            left,right = inverse.get(row["left_graph"],row["left_graph"]),inverse.get(row["right_graph"],row["right_graph"])
            pair = rank.loc[(left,right)]
            for column, saved in (("common_node_count","common_node_count"),("kendall_tau_b","kendall_tau"),("spearman_rho","spearman_rho"),("rank_displacement_mean","rank_displacement_mean"),("rank_displacement_median","rank_displacement_median"),("rank_displacement_p90","rank_displacement_p90")):
                if saved in row:check(f"{discipline}:{left}:{right}:{column}",np.isclose(pair[column],row[saved],rtol=1e-10,atol=1e-10,equal_nan=True))
            common = eligible[left].index.intersection(eligible[right].index)
            # Independent benchmark: original saved scores, not newly computed scores.
            orders=[sorted(common,key=lambda doi:(-eligible[name][doi],doi)) for name in (left,right)]
            for prefix,k in (("top_fraction",max(1,int(.1*len(common)))),("top10",min(10,len(common))),("top20",min(20,len(common)))):
                overlap=len(set(orders[0][:k]) & set(orders[1][:k]))
                check(f"{discipline}:{left}:{right}:{prefix}:fixed_overlap",pair[prefix+"_overlap_count"]==overlap)
                expanded=[{doi for doi in common if eligible[name][doi]>=eligible[name][order[k-1]]} for name,order in zip((left,right),orders)]
                for suffix,value in (("left_size",len(expanded[0])),("right_size",len(expanded[1])),("jaccard",len(expanded[0]&expanded[1])/len(expanded[0]|expanded[1]))):
                    check(f"{discipline}:{left}:{right}:{prefix}:expanded_{suffix}",np.isclose(pair[f"{prefix}_tie_expanded_{suffix}"],value,rtol=1e-12,atol=1e-12))
                historical_field="overlap_count" if prefix=="top_fraction" else prefix+"_overlap_count"
                if historical_field in row and row[historical_field]!=overlap:
                    corrections.append({"discipline":discipline,"left":left,"right":right,"cutoff":prefix,"historical_overlap":row[historical_field],"doi_ordered_overlap":overlap})
    for file in ("citing_layer_audit.csv","seed_availability.csv","target_set_metrics.csv","network_convergence.csv","ranking_robustness_metrics.csv","citing_swap_ranking_metrics.csv","opencitations_citing_doi_edges.csv"):
        old, new=read(package/"historical_robustness"/file),read(recomputed/"robustness"/file)
        check(f"robustness:{file}:rows",len(old)==len(new))
        # Stored outputs and driver have deterministic row ordering.
        for column in old.select_dtypes(include="number"):
            check(f"robustness:{file}:{column}",np.allclose(new[column],old[column],rtol=1e-10,atol=1e-10,equal_nan=True))
    networks=read(recomputed/"robustness/network_convergence.csv")
    check("robustness:all_30_converged",len(networks)==30 and networks.converged.all())
    # Check Table 4 expanded percentage-cutoff diagnostics against frozen rank details.
    metrics=read(recomputed/"robustness/ranking_robustness_metrics.csv")
    for row in metrics.to_dict("records"):
        detail=read(package/"historical_robustness"/row['discipline']/f"{row['citing_layer']}_{row['left_reference']}_vs_{row['right_reference']}_ranks.csv")
        for prefix,p in (("top10percent",.1),("top20percent",.2)):
            k=max(1,int(p*len(detail)))
            orders=[detail.sort_values([score,'doi'],ascending=[False,True]) for score in ('left_score','right_score')]
            expanded=[set(detail.loc[detail[score]>=order.iloc[k-1][score],'doi']) for score,order in zip(('left_score','right_score'),orders)]
            value=len(expanded[0]&expanded[1])/len(expanded[0]|expanded[1])
            check(f"robustness:{row['discipline']}:{row['citing_layer']}:{row['left_reference']}:{row['right_reference']}:{prefix}:expanded_jaccard",np.isclose(row[prefix+'_tie_expanded_jaccard'],value,rtol=1e-12,atol=1e-12))
    output.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame(checks)
    frame.to_csv(output/'checks.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(corrections).to_csv(output/'historical_cutoff_differences.csv',index=False,encoding='utf-8-sig')
    summary={"software_version":"0.1.1","network_requests":0,"checks":len(checks),"failures":int((~frame.passed).sum()),"passed":bool(frame.passed.all()),"primary_disciplines":5,"robustness_networks":30,"reference_pair_comparisons":30,"citing_swap_comparisons":15,"historical_cutoff_policy":"Historic files retained unchanged; fixed and expanded cutoffs independently benchmarked from original saved scores using manuscript DOI ordering."}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)
    if not frame.passed.all():print(frame.loc[~frame.passed].to_string(index=False),flush=True)
    return 0 if frame.passed.all() else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--recomputed',type=Path,default=Path('recomputed'))
    parser.add_argument('--output',type=Path,default=Path('validation'))
    args=parser.parse_args()
    raise SystemExit(validate(args.package_root,args.recomputed,args.output))
