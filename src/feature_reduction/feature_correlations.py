"""
Spearman correlation between each feature and answer correctness, per model and for the share of
models that answered correctly ("All"). Writes a CSV with all features and a LaTeX table of the
--top features by |rho| with "All".

Usage:
  python feature_correlations.py --features features_14729_reduced_mean.csv --eval answers_eval_14729.jsonl \
      --output feature_correlations.csv --latex feature_correlations.tex --top 25
"""

import argparse
import json

import pandas as pd

from reduce_features import DISPLAY, GROUP, SHORT


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--features", required=True, help="reduced features CSV")
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
    cols = [c for c in feats if c in DISPLAY and d[c].nunique() > 1]
    if not cols:
        raise SystemExit(f"no feature columns found in {args.features}")

    res = pd.DataFrame({t: [d[c].corr(d[t], method="spearman") for c in cols] for t in ["All"] + models}, index=cols)
    res.insert(0, "group", [GROUP[c] for c in cols])
    res.insert(0, "short_name", [SHORT[c] for c in cols])
    res.insert(0, "display_name", [DISPLAY[c] for c in cols])
    res = res.reindex(res["All"].abs().sort_values(ascending=False).index)
    res.round(3).to_csv(args.output, index_label="column")
    a = res["All"].abs()
    print(f"{len(d):,} questions, {len(models)} models, {len(cols)} features; "
          f"|rho| >= 0.1: {(a >= 0.1).sum()}, >= 0.2: {(a >= 0.2).sum()}")
    print(res.drop(columns="display_name").head(args.top).round(3).to_string(index=False))

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
