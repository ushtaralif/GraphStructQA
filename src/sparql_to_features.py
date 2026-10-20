"""
Compute the dataset features (the columns of data/features_14729.csv) for your own SPARQL queries.

Requires a Wikidata SPARQL endpoint (QLever) and Apache Jena 6.2.0 with Java 21.

Examples:
  python src/sparql_to_features.py --endpoint <QLever URL> --sparql "SELECT ?x WHERE { wd:Q42 wdt:P69 ?x }" \
      --question "Where was Douglas Adams educated?"
  python src/sparql_to_features.py --endpoint <QLever URL> --input my_queries.jsonl --output my_features.csv
"""

import argparse, csv, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset_generation import features_wikidata as fw, features_jena as fj
from dataset_generation.merge_datasets import FEATURES


def sparql_to_features(rows, endpoint, jena_home, cache_dir="wikidata_cache", work_dir=".jena_build"):
    """rows: [{"id", "sparql", "question" (optional)}] -> {id: {feature: value}}"""
    parsed = [fw.query_features(r.get("question", ""), r["sparql"]) for r in rows]
    qids = sorted({q for _, qs, _ in parsed for q in qs})
    pids = sorted({p for _, _, ps in parsed for p in ps})
    cache = Path(cache_dir); cache.mkdir(parents=True, exist_ok=True)
    ql = fw.QLever(endpoint)
    props = fw.cached(cache / "properties.jsonl", "pid", pids, fw.property_features, ql, 8)
    ents = fw.cached(cache / "entities.jsonl", "qid", qids, fw.entity_features, ql, 8)
    jena = fj.run_jena(rows, jena_home, work_dir)
    out = {}
    for r in rows:
        if jena[r["id"]]["status"] != "ok":
            raise ValueError(f"Jena could not parse query {r['id']}")
        out[r["id"]] = {**fw.question_features(r, ents, props), **fj.features(jena[r["id"]])}
    return out


def fmt(col, v):
    return fw.fmt(col, v) if col in fw.COLUMNS else fj.fmt(col, v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sparql", help="one SPARQL query")
    g.add_argument("--input", help="JSON/JSONL with id, sparql and optionally question")
    ap.add_argument("--question", default="", help="natural-language question (for --sparql)")
    ap.add_argument("--endpoint", required=True, help="QLever Wikidata SPARQL endpoint URL")
    ap.add_argument("--jena-home", default=os.environ.get("JENA_HOME"))
    ap.add_argument("--output", default=None, help="CSV (default: print to stdout)")
    args = ap.parse_args()
    if not args.jena_home:
        sys.exit("set --jena-home or JENA_HOME")

    rows = (fw.load_questions([args.input]) if args.input
            else [{"id": "q1", "sparql": args.sparql, "question": args.question}])
    if any(not r.get("question") for r in rows):
        print("warning: no question text -> question length = 0", file=sys.stderr)
    feats = sparql_to_features(rows, args.endpoint, args.jena_home)

    f = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    w = csv.writer(f)
    w.writerow(["id"] + FEATURES)
    for r in rows:
        w.writerow([r["id"]] + [fmt(c, feats[r["id"]][c]) for c in FEATURES])


if __name__ == "__main__":
    main()
