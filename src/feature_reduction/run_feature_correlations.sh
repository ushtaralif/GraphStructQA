#!/usr/bin/env bash
# Correlation of the mean features with answer correctness -> data/feature_reduction/feature_correlations.{csv,tex}
# Usage: bash run_feature_correlations.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"   # resource_paper/
DATA="$ROOT/data"
OUT="$DATA/feature_reduction"

python "$ROOT/src/feature_reduction/feature_correlations.py" \
    --features "$OUT/features_14729_reduced_mean.csv" --eval "$DATA/answers_eval_14729.jsonl" \
    --output "$OUT/feature_correlations.csv" --latex "$OUT/feature_correlations.tex" --top 25
