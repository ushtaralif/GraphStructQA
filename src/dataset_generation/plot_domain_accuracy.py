"""
Figure: answer accuracy per question domain and model, for both judges.

Two heatmaps side by side (GPT-5.4-mini, Claude Haiku 5.5): rows are the domains of
sparql_domain_classifier.py (query_domain) plus "All", columns are the models plus their
mean; cells show the accuracy (% of answers judged correct, classes 1-3). Domains are
ordered by the GPT mean accuracy in both panels.

Usage:
  python plot_domain_accuracy.py --answers answers_eval_14729.jsonl \
      --domains dataset_with_domains.json --output-dir figures
Output: <output-dir>/accuracy_by_domain.{pdf,png} and accuracy_by_domain.csv
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

JUDGES = [("GPT-5.4-mini", "eval_"), ("Claude Haiku 5.5", "claude_eval_")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", required=True, help="answers_eval_gpt_claude_14729.jsonl")
    ap.add_argument("--domains", required=True, help="output of sparql_domain_classifier.py (id, query_domain)")
    ap.add_argument("--output-dir", default="figures")
    args = ap.parse_args()

    domain = {r["id"]: r["query_domain"] for r in json.load(open(args.domains, encoding="utf-8"))}
    rows = [json.loads(l) for l in open(args.answers, encoding="utf-8") if l.strip()]
    models = [k[:-len("-answer")] for k in rows[0] if k.endswith("-answer")]
    recs = [(domain[r["id"]], m, judge, r[prefix + m]["correct"])
            for r in rows for m in models for judge, prefix in JUDGES if r.get(prefix + m)]
    df = pd.DataFrame(recs, columns=["domain", "model", "judge", "correct"])
    n = pd.Series(domain).value_counts()

    tables = {}
    for judge, _ in JUDGES:
        d = df[df.judge == judge]
        t = 100 * d.pivot_table(index="domain", columns="model", values="correct", aggfunc="mean")[models]
        t["Mean"] = t.mean(axis=1)
        t.loc["All"] = list(100 * d.groupby("model").correct.mean()[models]) + [np.nan]
        t.loc["All", "Mean"] = t.loc["All", models].mean()
        tables[judge] = t
    order = tables[JUDGES[0][0]].drop("All").sort_values("Mean", ascending=False).index.tolist() + ["All"]
    cols = models + ["Mean"]

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pd.concat({j: t.loc[order, cols] for j, t in tables.items()}, axis=1).assign(n=n.reindex(order).fillna(len(domain))) \
        .round(1).to_csv(out / "accuracy_by_domain.csv")

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharey=True)
    for ax, (judge, _) in zip(axes, JUDGES):
        v = tables[judge].loc[order, cols].to_numpy()
        ax.imshow(v, cmap="Blues", vmin=20, vmax=90, aspect="auto")
        for i in range(v.shape[0]):
            for j in range(v.shape[1]):
                ax.text(j, i, f"{v[i, j]:.1f}", ha="center", va="center", fontsize=8,
                        color="white" if v[i, j] > 65 else "#1a1a1a",
                        fontweight="bold" if order[i] == "All" or cols[j] == "Mean" else "normal")
        ax.set_xticks(range(len(cols)), cols, rotation=30, ha="right", fontsize=9)
        ax.axhline(len(order) - 1.5, color="white", lw=3)      # separate "All"
        ax.axvline(len(cols) - 1.5, color="white", lw=3)       # separate "Mean"
        ax.set_title(f"Judge: {judge}", fontsize=10)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
    labels = [f"{d} (n={len(domain) if d == 'All' else n[d]:,})" for d in order]
    axes[0].set_yticks(range(len(order)), labels, fontsize=9)
    fig.suptitle("Accuracy (%) by question domain and model", fontsize=11)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(out / f"accuracy_by_domain.{ext}", dpi=200, bbox_inches="tight")
    print("Saved:", out / "accuracy_by_domain.pdf", out / "accuracy_by_domain.png", out / "accuracy_by_domain.csv")


if __name__ == "__main__":
    main()
