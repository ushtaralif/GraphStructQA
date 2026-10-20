#!/usr/bin/env bash
# Feature reduction -> data/feature_reduction/features_14729_reduced_mean.csv
# (constant and duplicate query features removed, mean of each entity / property statistic)
# Usage: bash run_reduce_features.sh [raw features CSV]   default: data/features_14729New.csv
#        (merge_datasets.py writes the raw features as features_14729.csv)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"   # resource_paper/
DATA="$ROOT/data"
OUT="$DATA/feature_reduction"
mkdir -p "$OUT"
INPUT="${1:-$DATA/features_14729New.csv}"

python "$ROOT/src/feature_reduction/reduce_features.py" \
    --input "$INPUT" \
    --output "$OUT/features_14729_reduced_mean.csv"
