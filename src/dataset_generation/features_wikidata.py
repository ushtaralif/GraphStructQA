"""
Wikidata and query features of the resource (61 of the 86 features).
"""

import argparse
import csv
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

QID_RE = re.compile(r'\bQ[1-9][0-9]*\b')
PID_RE = re.compile(r'\bP[1-9][0-9]*\b')
VAR_RE = re.compile(r'(?<![\w])[\?\$][A-Za-z_][A-Za-z0-9_]*')
INCOMING_DEGREE_CAP = 1_000_000

QUERY_FEATURES = ["distinct_entity_count", "distinct_property_count", "variable_count", "optional_count",
                  "union_count", "filter_count", "subquery_count", "aggregation_count", "group_by_count",
                  "order_by_count", "query_chars", "query_lines", "question_chars", "question_words"]
ENTITY_FIELDS = ["num_statements", "num_references", "num_properties", "num_sitelinks", "num_aliases",
                 "num_languages", "outgoing_degree", "incoming_degree_capped", "entity_entropy", "entity_obscurity"]
PROPERTY_FIELDS = ["property_frequency", "distinct_value_count", "property_entropy", "property_subject_count",
                   "property_obscurity"]
AGGS = ["mean", "min", "max"]
COLUMNS = ([f"query__{f}" for f in QUERY_FEATURES] + ["entity__has_entity"]
           + [f"entity__{f}__{a}" for f in ENTITY_FIELDS for a in AGGS] + ["property__has_property"]
           + [f"property__{f}__{a}" for f in PROPERTY_FIELDS for a in AGGS])
INT_FIELDS = {"num_statements", "num_references", "num_properties", "num_sitelinks", "num_aliases", "num_languages",
              "outgoing_degree", "incoming_degree_capped", "property_frequency", "distinct_value_count",
              "property_subject_count"}
INT_COLUMNS = ({f"query__{f}" for f in QUERY_FEATURES} | {"entity__has_entity", "property__has_property"}
               | {f"{lvl}__{f}__{a}" for lvl in ("entity", "property") for f in INT_FIELDS for a in ("min", "max")})


# ---------------------------------------------------------------- query features (stage 20)
def remove_comments(s):
    """Remove '#' comments without damaging # inside <IRI> or strings."""
    out, in_iri, in_single, in_double, escape, i = [], False, False, False, False, 0
    while i < len(s):
        c = s[i]
        if escape:
            out.append(c)
            escape = False
            i += 1
            continue
        if c == "\\":
            out.append(c)
            escape = True
            i += 1
            continue
        if not in_single and not in_double:
            if c == "<":
                in_iri = True
            elif c == ">" and in_iri:
                in_iri = False
        if not in_iri:
            if c == "'" and not in_double:
                in_single = not in_single
            elif c == '"' and not in_single:
                in_double = not in_double
        if c == "#" and not in_iri and not in_single and not in_double:
            while i < len(s) and s[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_strings(s):
    """Replace string contents with spaces to reduce keyword false positives."""
    out, quote, escape = [], None, False
    for c in s:
        if escape:
            out.append(" ")
            escape = False
            continue
        if c == "\\" and quote:
            out.append(" ")
            escape = True
            continue
        if quote:
            if c == quote:
                quote = None
            out.append(" ")
            continue
        if c in ('"', "'"):
            quote = c
            out.append(" ")
        else:
            out.append(c)
    return "".join(out)


def count_keyword(s, pattern):
    return len(re.findall(pattern, s, flags=re.I))


def query_features(question, sparql):
    clean = remove_comments(sparql)
    kw = strip_strings(clean)
    qids = sorted(set(QID_RE.findall(clean)))
    pids = sorted(set(PID_RE.findall(clean)))
    aggs = sum(count_keyword(kw, rf'\b{f}\s*\(') for f in ("COUNT", "SUM", "AVG", "MIN", "MAX", "GROUP_CONCAT", "SAMPLE"))
    return {
        "distinct_entity_count": len(qids),
        "distinct_property_count": len(pids),
        "variable_count": len(set(VAR_RE.findall(clean))),
        "optional_count": count_keyword(kw, r'\bOPTIONAL\b'),
        "union_count": count_keyword(kw, r'\bUNION\b'),
        "filter_count": count_keyword(kw, r'\bFILTER\b'),
        "subquery_count": max(0, len(re.findall(r'\b(?:SELECT|ASK)\b', kw, flags=re.I)) - 1),
        "aggregation_count": aggs,
        "group_by_count": count_keyword(kw, r'\bGROUP\s+BY\b'),
        "order_by_count": count_keyword(kw, r'\bORDER\s+BY\b'),
        "query_chars": len(sparql),
        "query_lines": len(sparql.splitlines()),
        "question_chars": len(question),
        "question_words": len(question.split()),
    }, qids, pids


# ---------------------------------------------------------------- QLever
class QLever:
    def __init__(self, endpoint, timeout=300):
        self.endpoint, self.timeout = endpoint.rstrip("/"), timeout
        self.session = requests.Session()

    def rows(self, sparql, send=100):
        r = self.session.post(self.endpoint, data={"query": sparql, "send": str(send)},
                              headers={"Accept": "application/qlever-results+json"}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def export(self, sparql, timeout=60):
        r = self.session.post(self.endpoint, data={"query": sparql, "action": "qlever_json_export"}, timeout=timeout)
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
        return r.json()


def strip_rdf_literal(x):
    if x is None or isinstance(x, (int, float, bool)):
        return x
    s = str(x)
    m = re.match(r'^"(.*)"@[A-Za-z0-9-]+$', s, re.S) or re.match(r'^"(.*)"\^\^<[^>]+>$', s, re.S)
    if m:
        return m.group(1)
    return s[1:-1] if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else s


def as_float(x):
    if x is None:
        return None
    x = strip_rdf_literal(x)
    try:
        return float(x)
    except Exception:
        m = re.search(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', str(x))
        return float(m.group(0)) if m else None


def first_row(data):
    res = data.get("res") or []
    return res[0] if res else []


def literal_int(v):
    """Integer from a QLever export cell (typed literal or plain)."""
    if v is None:
        return 0
    if isinstance(v, str) and '"' in v:
        return int(v.split('"')[1])
    return int(v)


DIRECT = '"^http://www.wikidata.org/prop/direct/P[0-9]+$"'
CLAIM = '"^http://www.wikidata.org/prop/P[0-9]+$"'


def entity_features(ql, qid):
    """Stage 21 entity statistics + stage 25 sitelink count + stage 28 obscurity."""
    row = first_row(ql.rows(f"""PREFIX wd: <http://www.wikidata.org/entity/>
SELECT (COUNT(DISTINCT ?statement) AS ?numStatements) (COUNT(DISTINCT ?claimProperty) AS ?numProperties)
WHERE {{ wd:{qid} ?claimProperty ?statement . FILTER(REGEX(STR(?claimProperty), {CLAIM})) }}""", send=10))
    num_statements = as_float(row[0]) if len(row) > 0 else 0
    num_properties = as_float(row[1]) if len(row) > 1 else 0
    row = first_row(ql.rows(f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT (COUNT(DISTINCT ?ref) AS ?numReferences)
WHERE {{ wd:{qid} ?claimProperty ?statement . FILTER(REGEX(STR(?claimProperty), {CLAIM}))
  ?statement prov:wasDerivedFrom ?ref . }}""", send=10))
    num_references = as_float(row[0]) if row else 0
    row = first_row(ql.rows(f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX schema: <http://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT (COUNT(DISTINCT ?alias) AS ?numAliases) (COUNT(DISTINCT ?lang) AS ?numLanguages)
WHERE {{
  {{ ?article schema:about wd:{qid} . }} UNION {{ wd:{qid} skos:altLabel ?alias . }} UNION
  {{ wd:{qid} ?lp ?lex . VALUES ?lp {{ rdfs:label skos:altLabel schema:description }}
     BIND(LANG(?lex) AS ?lang) FILTER(?lang != "") }} UNION
  {{ ?entityData schema:about wd:{qid} ; schema:dateModified ?modified . }}
}}""", send=10))
    num_aliases = as_float(row[0]) if len(row) > 0 else 0
    num_languages = as_float(row[1]) if len(row) > 1 else 0
    row = first_row(ql.rows(f"""PREFIX wd: <http://www.wikidata.org/entity/>
SELECT (COUNT(*) AS ?n) WHERE {{ wd:{qid} ?p ?o . FILTER(REGEX(STR(?p), {DIRECT})) }}""", send=10))
    outgoing = as_float(row[0]) if row else 0
    row = first_row(ql.rows(f"""PREFIX wd: <http://www.wikidata.org/entity/>
SELECT (COUNT(*) AS ?n) WHERE {{ {{ SELECT ?s ?p WHERE {{ ?s ?p wd:{qid} . FILTER(REGEX(STR(?p), {DIRECT})) }}
  LIMIT {INCOMING_DEGREE_CAP} }} }}""", send=10))
    incoming = int(as_float(row[0]) if row else 0)
    counts = [c for r in ql.rows(f"""PREFIX wd: <http://www.wikidata.org/entity/>
SELECT ?p (COUNT(?o) AS ?c) WHERE {{ wd:{qid} ?p ?o . FILTER(REGEX(STR(?p), {DIRECT})) }} GROUP BY ?p""",
                                  send=100000).get("res", [])
              if len(r) >= 2 and (c := as_float(r[1])) is not None and c > 0]
    total = sum(counts)
    entropy = -sum((c / total) * math.log2(c / total) for c in counts) if total > 0 else 0.0
    # Sitelinks: articles that are part of a site (the stage-21 UNION count is not used).
    data = ql.export(f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX schema: <http://schema.org/>
SELECT ?entity (COUNT(?article) AS ?n) WHERE {{ VALUES ?entity {{ wd:{qid} }}
  OPTIONAL {{ ?article schema:about ?entity ; schema:isPartOf ?site . }} }} GROUP BY ?entity""")
    sitelinks = literal_int(data["res"][0][1])
    props = int(num_properties or 0)
    return {"qid": qid, "num_statements": int(num_statements or 0), "num_references": int(num_references or 0),
            "num_properties": props, "num_sitelinks": sitelinks, "num_aliases": int(num_aliases or 0),
            "num_languages": int(num_languages or 0), "outgoing_degree": int(outgoing or 0),
            "incoming_degree_capped": incoming, "entity_entropy": entropy,
            "entity_obscurity": 1.0 / (1.0 + math.log1p(sitelinks) + math.log1p(props))}


def property_features(ql, pid):
    """Stage 21 exact value statistics (frequency-of-frequencies) + stage 27 subjects and obscurity."""
    data = ql.rows(f"""PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT ?count (COUNT(*) AS ?numValues) WHERE {{ {{ SELECT ?value (COUNT(*) AS ?count)
  WHERE {{ ?entity wdt:{pid} ?value . }} GROUP BY ?value }} }} GROUP BY ?count ORDER BY ?count""", send=1_000_000)
    rows = data.get("res", [])
    if data.get("resultSizeTotal") is not None and len(rows) != int(data["resultSizeTotal"]):
        raise RuntimeError(f"{pid}: incomplete frequency buckets")
    buckets = [(int(c), int(n)) for r in rows if len(r) >= 2
               and (c := as_float(r[0])) is not None and c > 0 and (n := as_float(r[1])) is not None and n > 0]
    if len(buckets) != len(rows):
        raise RuntimeError(f"{pid}: failed to parse all frequency buckets")
    distinct = sum(n for c, n in buckets)
    freq = sum(c * n for c, n in buckets)
    entropy = (math.log2(freq) - sum(n * c * math.log2(c) for c, n in buckets) / freq) if freq > 0 else 0.0
    subjects = literal_int(ql.export(f"""PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT (COUNT(*) AS ?n) WHERE {{ {{ SELECT ?s WHERE {{ ?s wdt:{pid} ?o . }} GROUP BY ?s }} }}""")["res"][0][0])
    return {"pid": pid, "property_frequency": freq, "distinct_value_count": distinct, "property_entropy": entropy,
            "property_subject_count": subjects, "property_obscurity": 1.0 / (1.0 + math.log1p(subjects))}


def cached(path, key, ids, fn, ql, workers, retries=5):
    """{id: record}; computes missing ids (with retries) and appends them to the JSONL cache."""
    cache = {}
    if path.exists():
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                cache[r[key]] = r
    todo = [i for i in ids if i not in cache]

    def job(i):
        for attempt in range(1, retries + 1):
            try:
                return fn(ql, i)
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError(f"{key} {i} failed after {retries} attempts: {err}")

    with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(workers) as ex:
        for n, r in enumerate(ex.map(job, todo), 1):
            cache[r[key]] = r
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            if n % 200 == 0 or n == len(todo):
                f.flush()
                print(f"[{key}] {n:,}/{len(todo):,}", flush=True)
    return cache


def aggregate(values):
    return {"mean": sum(values) / len(values), "min": min(values), "max": max(values)}


def question_features(row, entities, properties):
    qf, qids, pids = query_features(row.get("question", ""), row.get("sparql", ""))
    out = {f"query__{k}": v for k, v in qf.items()}
    out["entity__has_entity"] = 1 if qids else 0
    for f in ENTITY_FIELDS:
        agg = aggregate([entities[q][f] for q in qids]) if qids else dict.fromkeys(AGGS, 0.0)
        out.update({f"entity__{f}__{a}": agg[a] for a in AGGS})
    out["property__has_property"] = 1 if pids else 0
    for f in PROPERTY_FIELDS:
        agg = aggregate([properties[p][f] for p in pids]) if pids else dict.fromkeys(AGGS, 0.0)
        out.update({f"property__{f}__{a}": agg[a] for a in AGGS})
    return out


def load_questions(paths, id_prefix="", ids_from=None):
    rows = []
    for p in paths:
        text = Path(p).read_text(encoding="utf-8")
        recs = json.loads(text) if text.lstrip().startswith("[") else [json.loads(l) for l in text.split("\n") if l.strip()]
        rows += [{**r, "id": id_prefix + r["id"]} for r in recs]
    if ids_from:
        keep = {json.loads(l)["id"] for l in open(ids_from, encoding="utf-8") if l.strip()}
        rows = [r for r in rows if r["id"] in keep]
    assert len({r["id"] for r in rows}) == len(rows), "duplicate ids"
    return rows


def fmt(col, v):
    return str(int(v)) if col in INT_COLUMNS else repr(float(v))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", nargs="+", required=True, help="JSON/JSONL files with id, question, sparql")
    ap.add_argument("--id-prefix", default="", help="prefix added to the input ids")
    ap.add_argument("--ids-from", default=None, help="keep only ids in this JSONL (e.g. dataset_14729.jsonl)")
    ap.add_argument("--endpoint", default="http://localhost:7001", help="QLever Wikidata endpoint")
    ap.add_argument("--cache-dir", default="wikidata_cache")
    ap.add_argument("--workers", type=int, default=8, help="parallel QLever requests")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    rows = load_questions(args.input, args.id_prefix, args.ids_from)
    parsed = [query_features(r.get("question", ""), r.get("sparql", "")) for r in rows]
    qids = sorted({q for _, qs, _ in parsed for q in qs})
    pids = sorted({p for _, _, ps in parsed for p in ps})
    print(f"{len(rows):,} questions, {len(qids):,} entities, {len(pids):,} properties", flush=True)

    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    ql = QLever(args.endpoint)
    properties = cached(cache / "properties.jsonl", "pid", pids, property_features, ql, args.workers)
    entities = cached(cache / "entities.jsonl", "qid", qids, entity_features, ql, args.workers)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id"] + COLUMNS)
        for r in rows:
            v = question_features(r, entities, properties)
            w.writerow([r["id"]] + [fmt(c, v[c]) for c in COLUMNS])
    print(f"{len(rows):,} questions, {len(COLUMNS)} Wikidata/query features -> {args.output}")


if __name__ == "__main__":
    main()
