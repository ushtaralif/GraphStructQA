"""
Spearman correlation between each feature and answer correctness, per model and for the share of
models that answered correctly ("All"). Writes a CSV with all features and a LaTeX table of the
--top features by |rho| with "All".

Usage:
  python feature_correlations.py --features features_14729.csv --eval answers_eval_14729.jsonl \
      --output feature_correlations.csv --latex feature_correlations.tex --top 25
"""

import argparse
import json

import pandas as pd

SHORT = {  # names in the LaTeX table
    "query_num_triple_patterns": "Triple patterns", "query_num_entities": "Entities",
    "query_num_properties": "Properties", "query_num_variables": "Variables", "query_num_optional": "OPTIONAL",
    "query_num_union": "UNION", "query_num_filter": "FILTER", "query_num_subqueries": "Subqueries",
    "query_num_aggregates": "Aggregates", "query_num_group_by": "GROUP BY", "query_num_order_by": "ORDER BY",
    "query_length_chars": "Query length", "question_length_words": "Question length", "query_is_ask": "ASK query",
    "query_num_computed_values": "BIND", "query_num_distinct": "DISTINCT", "query_num_limit_offset": "LIMIT / OFFSET",
    "query_num_property_paths": "Property paths", "query_has_having": "HAVING",
    "entity_num_statements_mean": "Statements", "entity_num_references_mean": "References",
    "entity_num_properties_mean": "Properties", "entity_num_sitelinks_mean": "Sitelinks",
    "entity_num_aliases_mean": "Aliases", "entity_num_languages_mean": "Label languages",
    "entity_outgoing_degree_mean": "Outgoing degree", "entity_incoming_degree_mean": "Incoming degree",
    "entity_entropy_mean": "Entity entropy", "entity_obscurity_mean": "Entity obscurity",
    "has_property": "Has property", "property_num_triples_mean": "Triples",
    "property_num_values_mean": "Distinct values", "property_entropy_mean": "Property entropy",
    "property_num_subjects_mean": "Subjects", "property_obscurity_mean": "Property obscurity",
}


def group(c):
    if c.startswith("entity_"):
        return "Entity"
    return "Property" if c.startswith("property_") or c == "has_property" else "Query"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--features", required=True, help="features_14729.csv")
    ap.add_argument("--eval", required=True, help="answers_eval_14729.jsonl")
    ap.add_argument("--output", required=True, help="CSV with rho of every feature")
    ap.add_argument("--latex", default=None, help="LaTeX table of the top features")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    feats = pd.read_csv(args.features)
    rows = [json.loads(line) for line in open(args.eval, encoding="utf-8")]
    models = [k[len("eval_"):] for k in rows[0] if k.startswith("eval_")]
    y = pd.DataFrame({"id": [r["id"] for r in rows],
                      **{m: [r[f"eval_{m}"]["correct"] for r in rows] for m in models}})
    y["All"] = y[models].mean(axis=1)
    d = feats.merge(y, on="id", validate="1:1")
    cols = [c for c in feats if c in SHORT and d[c].nunique() > 1]
    if not cols:
        raise SystemExit(f"no feature columns found in {args.features}")

    res = pd.DataFrame({t: [d[c].corr(d[t], method="spearman") for c in cols] for t in ["All"] + models}, index=cols)
    res.insert(0, "group", [group(c) for c in cols])
    res.insert(0, "short_name", [SHORT[c] for c in cols])
    res = res.reindex(res["All"].abs().sort_values(ascending=False).index)
    res.round(3).to_csv(args.output, index_label="column")
    a = res["All"].abs()
    print(f"{len(d):,} questions, {len(models)} models, {len(cols)} features; "
          f"|rho| >= 0.1: {(a >= 0.1).sum()}, >= 0.2: {(a >= 0.2).sum()}")
    print(res.head(args.top).round(3).to_string(index=False))

    if args.latex:
        top = res.head(args.top)
        lines = [r"\begin{tabular}{ll" + "r" * (len(models) + 1) + "}", r"\toprule",
                 "Feature & Group & All & " + " & ".join(models) + r" \\", r"\midrule"]
        lines += [f"{r['short_name']} & {r['group']} & " + " & ".join(f"{r[t]:+.2f}" for t in ["All"] + models)
                  + r" \\" for _, r in top.iterrows()]
        lines += [r"\bottomrule", r"\end{tabular}"]
        with open(args.latex, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).replace("_", r"\_") + "\n")
        print("LaTeX:", args.latex)


if __name__ == "__main__":
    main()
