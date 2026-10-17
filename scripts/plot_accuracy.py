
import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

LABELS = {1: "1 Perfectly accurate", 2: "2 Correct, other entity", 3: "3 Correct + redundant",
          4: "4 Intrinsic error", 5: "5 Hallucination", 6: "6 Irrelevant", 7: "7 Completely inaccurate"}

COLORS = {3: "#86b6ef", 2: "#3987e5", 1: "#1c5cab", 4: "#f2a19c", 5: "#e86b67", 6: "#d03b3b", 7: "#9e2423"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e6e3"

plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans", "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": INK})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="answers_eval_14729.jsonl")
    ap.add_argument("--output-dir", default="figures")
    args = ap.parse_args()
    OUT = Path(args.output_dir)
    rows = [json.loads(line) for line in open(args.input, encoding="utf-8")]
    models = [k.removeprefix("eval_") for k in rows[0] if k.startswith("eval_")]
    n = len(rows)
    pct = {m: {c: 100 * sum(r[f"eval_{m}"]["class"] == c for r in rows) / n for c in range(1, 8)} for m in models}
    acc = {m: sum(pct[m][c] for c in (1, 2, 3)) for m in models}
    order = sorted(models, key=lambda m: acc[m])  # best on top
    y = np.arange(len(order))

    fig, ax = plt.subplots(figsize=(6.0, 2.9))
    h = 0.62
    for i, m in enumerate(order):
        left = 0.0
        for c in (3, 2, 1):
            w = pct[m][c]
            ax.barh(i, w, h, left=left, color=COLORS[c], edgecolor="white", linewidth=1.0)
            if w >= 7:
                ax.text(left + w / 2, i, f"{w:.0f}", ha="center", va="center", fontsize=6.5,
                        color="white" if c == 1 else INK)
            left += w
        ax.text(left + 1.2, i, f"{acc[m]:.1f}%", ha="left", va="center", fontsize=7.5, color=INK, fontweight="bold")
        right = 0.0
        for c in (4, 5, 6, 7):
            w = pct[m][c]
            ax.barh(i, -w, h, left=-right, color=COLORS[c], edgecolor="white", linewidth=1.0)
            if w >= 7:
                ax.text(-right - w / 2, i, f"{w:.0f}", ha="center", va="center", fontsize=6.5,
                        color="white" if c >= 6 else INK)
            right += w
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(order)
    ax.set_xlim(-62, 70)
    ax.set_xticks(range(-60, 61, 20))
    ax.set_xticklabels([f"{abs(t)}" for t in range(-60, 61, 20)])
    ax.set_xlabel(f"% of {n:,} questions   (← incorrect: classes 4–7  |  correct: classes 1–3 →)")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title(f"GPT-5.4-mini 7-point judgment of the answers to all {n:,} questions", fontsize=8.5, loc="left",
                 color=INK)

    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[c]) for c in (1, 2, 3, 4, 5, 6, 7)]
    fig.legend(handles, [LABELS[c] for c in (1, 2, 3, 4, 5, 6, 7)], loc="lower center", ncol=4, frameon=False,
               fontsize=6.8, bbox_to_anchor=(0.55, -0.01), handlelength=1.1, columnspacing=1.2)

    fig.subplots_adjust(left=0.16, right=0.98, top=0.9, bottom=0.27)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"judge_7point.{ext}", dpi=300)
    print("Saved:", OUT / "judge_7point.pdf")
    if any(k.startswith("claude_eval_") for k in rows[0]):
        plot_judges(rows, models, OUT)


GPT_COLOR, CLAUDE_COLOR = "#2a78d6", "#eb6834"


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe)


def plot_judges(rows, models, out):
    """Accuracy per model judged by GPT-5.4-mini and Claude Haiku 5.5 (questions judged by both)."""
    res = {}
    for m in models:
        pairs = [(r[f"eval_{m}"]["correct"], r[f"claude_eval_{m}"]["correct"]) for r in rows
                 if r.get(f"eval_{m}") and r.get(f"claude_eval_{m}")]
        g, c = [p[0] for p in pairs], [p[1] for p in pairs]
        res[m] = {"n": len(pairs), "gpt": 100 * sum(g) / len(g), "claude": 100 * sum(c) / len(c), "kappa": kappa(g, c)}
    order = sorted(models, key=lambda m: res[m]["gpt"])  # best (GPT) on top
    y = np.arange(len(order))
    h = 0.36
    fig, ax = plt.subplots(figsize=(6.0, 2.9))
    for i, m in enumerate(order):
        for dy, key, color in ((h / 2 + 0.02, "gpt", GPT_COLOR), (-h / 2 - 0.02, "claude", CLAUDE_COLOR)):
            v = res[m][key]
            ax.barh(i + dy, v, h, color=color, edgecolor="white", linewidth=1.0)
            ax.text(v + 0.8, i + dy, f"{v:.1f}%", ha="left", va="center", fontsize=7, color=INK)
        ax.text(101, i, f"κ = {res[m]['kappa']:.2f}", ha="left", va="center", fontsize=7, color=MUTED)
    ax.set_yticks(y)
    ax.set_yticklabels(order)
    ax.set_xlim(0, 112)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel(f"accuracy (%, classes 1–3) on {min(r['n'] for r in res.values()):,} questions")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Accuracy by judge (same 7-point prompt); κ: agreement on correct / incorrect", fontsize=8.5,
                 loc="left", color=INK)
    handles = [plt.Rectangle((0, 0), 1, 1, color=GPT_COLOR), plt.Rectangle((0, 0), 1, 1, color=CLAUDE_COLOR)]
    fig.legend(handles, ["GPT-5.4-mini", "Claude Haiku 5.5"], loc="lower center", ncol=2, frameon=False,
               fontsize=7.5, bbox_to_anchor=(0.55, -0.01))
    fig.subplots_adjust(left=0.16, right=0.98, top=0.9, bottom=0.22)
    for ext in ("pdf", "png"):
        fig.savefig(out / f"accuracy_gpt_vs_claude.{ext}", dpi=300)
    plt.close(fig)
    for m in order[::-1]:
        print(f"{m:14s} n={res[m]['n']:,} GPT {res[m]['gpt']:.1f}% Claude {res[m]['claude']:.1f}% kappa {res[m]['kappa']:.2f}")
    print("Saved:", out / "accuracy_gpt_vs_claude.pdf")


if __name__ == "__main__":
    main()
