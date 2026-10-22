import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from typing import Dict, List, Optional

from property_classifier import META_PROPERTIES, PropertyClassifier

# ----------------------------------------------------------------------
# Property-ID extraction from raw SPARQL text
# ----------------------------------------------------------------------

_PREFIXED_PROP_RE = re.compile(r"\b(?:wdt|p|ps|pq|psv|pqv|wdno|wdtn)n?:(P\d+)\b")

_URI_PROP_RE = re.compile(
    r"wikidata\.org/prop/(?:direct(?:-normalized)?/|statement(?:/value)?/|"
    r"qualifier(?:/value)?/|reference(?:/value)?/)?(P\d+)\b"
)


def extract_properties(sparql: str) -> List[str]:
    """
    Return property IDs (e.g. ["P31", "P108"]) in order of first appearance
    in the SPARQL text, de-duplicated.
    """
    if not sparql:
        return []
    found: List[str] = []
    seen = set()
    for m in re.finditer(f"(?:{_PREFIXED_PROP_RE.pattern}|{_URI_PROP_RE.pattern})", sparql):
        pid = m.group(1) or m.group(2)
        if pid and pid not in seen:
            seen.add(pid)
            found.append(pid)
    return found


# ----------------------------------------------------------------------
# Dataset I/O
# ----------------------------------------------------------------------

_QUESTION_KEYS = ["question", "nl_question", "nlq", "utterance", "question_text", "nl"]
_SPARQL_KEYS = ["sparql", "sparql_query", "query", "sparql_wikidata", "masked_query"]


def _detect_field(sample: dict, candidates: List[str]) -> Optional[str]:
    lower_map = {k.lower(): k for k in sample.keys()}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    return None


def load_dataset(path: str) -> List[dict]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    # JSON array
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # common wrapper keys
            for key in ("data", "questions", "results", "records"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
    except json.JSONDecodeError:
        pass
    # JSON-lines fallback
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def save_dataset(path: str, rows: List[dict]):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        if not rows:
            open(path, "w").close()
            return
        fieldnames = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------
# Domain consolidation
# ----------------------------------------------------------------------

def consolidate_domain(domains: List[str], strategy: str) -> str:
    if not domains:
        return "Other"
    if strategy == "first":
        return domains[0]
    if strategy == "majority":
        counts = Counter(domains)
        top_count = max(counts.values())
        # tie-break: first property (in order of appearance) whose domain
        # has the top count
        for d in domains:
            if counts[d] == top_count:
                return d
        return domains[0]
    if strategy == "last-with-domain":
        with_domain = [d for d in domains if d != "Other"]
        return with_domain[-1] if with_domain else "Other"
    # "last"
    return domains[-1]


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Path to dataset (JSON array, JSON-lines, or CSV).")
    ap.add_argument("--output", required=True, help="Path to write the augmented dataset.")
    ap.add_argument("--question-field", default=None, help="Field/column name holding the NL question (auto-detected if omitted).")
    ap.add_argument("--sparql-field", default=None, help="Field/column name holding the SPARQL query (auto-detected if omitted).")
    ap.add_argument("--strategy", default="last-with-domain", choices=["last-with-domain", "last", "first", "majority"],
                     help="How to pick one query_domain when a query references multiple properties (default: last-with-domain).")
    ap.add_argument("--cache-path", default="data/cache/property_domains.json",
                     help="Local cache for property label/domain lookups (shared with the rest of the pipeline).")
    ap.add_argument("--summary-output", default=None,
                     help="Optional path to also write a domain-ablation-style summary JSON.")
    args = ap.parse_args()

    rows = load_dataset(args.input)
    if not rows:
        print(f"No rows loaded from {args.input}", file=sys.stderr)
        sys.exit(1)

    q_field = args.question_field or _detect_field(rows[0], _QUESTION_KEYS)
    s_field = args.sparql_field or _detect_field(rows[0], _SPARQL_KEYS)
    if not s_field:
        print(f"Could not detect a SPARQL field. Available keys: {list(rows[0].keys())}. "
              f"Pass --sparql-field explicitly.", file=sys.stderr)
        sys.exit(1)
    print(f"Using question field: {q_field!r}  |  SPARQL field: {s_field!r}")

    classifier = PropertyClassifier(cache_path=args.cache_path)

    # Pass 1: extract all property IDs across the whole dataset so we can
    # prefetch them in big batches (50 at a time) instead of one API call
    per_row_props: List[List[str]] = []
    all_pids = set()
    for row in rows:
        pids = extract_properties(row.get(s_field, ""))
        per_row_props.append(pids)
        all_pids.update(pids)

    meta = sorted(all_pids & set(META_PROPERTIES))
    print(f"Found {len(all_pids)} distinct property IDs across {len(rows)} queries; "
          f"{len(meta)} logical/taxonomical meta-properties are ignored ({', '.join(meta)}). Prefetching domains...")
    classifier.prefetch(sorted(all_pids - set(META_PROPERTIES)))

    # Pass 2: assign domains
    domain_counts = Counter()
    no_property_count = only_meta_count = 0
    for row, pids in zip(rows, per_row_props):
        domain_pids = [p for p in pids if p not in META_PROPERTIES]   # meta-properties are not used
        domains = [classifier.domain(pid) for pid in domain_pids]
        query_domain = consolidate_domain(domains, args.strategy)
        row["extracted_properties"] = pids
        row["domain_properties"] = domain_pids
        row["property_domains"] = domains
        row["query_domain"] = query_domain
        domain_counts[query_domain] += 1
        if not pids:
            no_property_count += 1
        elif not domain_pids:
            only_meta_count += 1

    save_dataset(args.output, rows)
    print(f"Wrote {len(rows)} rows -> {args.output}")

    if no_property_count:
        print(f"Warning: {no_property_count} rows had no extractable property "
              f"(check SPARQL prefixes / field name) and were labeled 'Other'.", file=sys.stderr)
    if only_meta_count:
        print(f"Note: {only_meta_count} rows use only meta-properties and were labeled 'Other'.", file=sys.stderr)

    print("\n--- Domain distribution (query_domain) ---")
    for domain, n in domain_counts.most_common():
        pct = 100.0 * n / len(rows)
        print(f"  {domain:<16} n={n:>5}  ({pct:5.1f}%)")

    if args.summary_output:
        summary = {
            "n_total": len(rows),
            "strategy": args.strategy,
            "domain_counts": dict(domain_counts),
            "rows_with_no_property": no_property_count,
            "rows_with_only_meta_properties": only_meta_count,
            "meta_properties": META_PROPERTIES,
        }
        with open(args.summary_output, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nWrote summary -> {args.summary_output}")


if __name__ == "__main__":
    main()
