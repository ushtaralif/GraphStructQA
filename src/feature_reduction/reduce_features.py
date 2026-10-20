"""
Reduce the 86 raw features to the released feature set and rename the columns.

  1. Features with the same value for every question are removed.
  2. Query features that count the same SPARQL construct as another query feature, or that
     describe the Jena algebra tree rather than the query, are removed (DROPPED below).
  3. For entity and property statistics only the mean over the entities / properties of the
     query is kept.

Usage:
  python reduce_features.py --input features_14729New.csv --output features_14729_reduced_mean.csv
"""

import argparse
import csv

import pandas as pd


QUERY = {
    "query__triple_pattern_count": ("query_num_triple_patterns", "Number of triple patterns",
                                    "Number of triple patterns, including property-path patterns (Jena parser)."),
    "query__distinct_entity_count": ("query_num_entities", "Number of entities", "Number of distinct Wikidata entities (Q-ids)."),
    "query__distinct_property_count": ("query_num_properties", "Number of properties",
                                       "Number of distinct Wikidata properties (P-ids)."),
    "query__variable_count": ("query_num_variables", "Number of variables", "Number of distinct variables (?x / $x) in the query text."),
    "query__optional_count": ("query_num_optional", "Number of OPTIONAL clauses", "Number of OPTIONAL keywords."),
    "query__union_count": ("query_num_union", "Number of UNION clauses", "Number of UNION keywords."),
    "query__filter_count": ("query_num_filter", "Number of FILTER clauses", "Number of FILTER keywords."),
    "query__subquery_count": ("query_num_subqueries", "Number of subqueries", "Number of nested SELECT / ASK queries."),
    "query__aggregation_count": ("query_num_aggregates", "Number of aggregates",
                                 "Number of aggregate calls (COUNT, SUM, AVG, MIN, MAX, GROUP_CONCAT, SAMPLE)."),
    "query__group_by_count": ("query_num_group_by", "Number of GROUP BY clauses", "Number of GROUP BY keywords."),
    "query__order_by_count": ("query_num_order_by", "Number of ORDER BY clauses", "Number of ORDER BY keywords."),
    "query__query_chars": ("query_length_chars", "Query length (characters)", "Number of characters of the SPARQL query."),
    "query__query_lines": ("query_length_lines", "Query length (lines)", "Number of lines of the SPARQL query."),
    "query__question_chars": ("question_length_chars", "Question length (characters)",
                              "Number of characters of the natural-language question."),
    "query__question_words": ("question_length_words", "Question length (words)",
                              "Number of words (whitespace-separated tokens) of the question."),
    "algebra__parse_success": ("algebra_parse_success", "Parsed by Jena", "1 if Apache Jena parsed the query, else 0."),
    "algebra__is_ask": ("query_is_ask", "ASK query (yes / no)", "1 if the query is an ASK (yes / no) query, else 0."),
    "algebra__jena_num_variables": ("query_num_result_variables", "Number of result variables",
                                    "Number of variables returned by a SELECT query (Jena result variables; 0 for ASK)."),
    "algebra__n_nodes": ("algebra_num_nodes", "Algebra size", "Number of operators in the Jena algebra tree."),
    "algebra__n_bgp": ("algebra_num_bgp", "Number of basic graph patterns", "Number of basic graph patterns (BGP operators)."),
    "algebra__n_join": ("algebra_num_joins", "Number of joins", "Number of join operators."),
    "algebra__n_filter": ("algebra_num_filters", "Number of filters (Jena)", "Number of filter operators."),
    "algebra__n_group": ("algebra_num_groupings", "Number of groupings (Jena)", "Number of group operators."),
    "algebra__n_extend": ("query_num_computed_values", "Number of computed values (BIND)", "Number of BIND assignments and SELECT expressions."),
    "algebra__n_project": ("algebra_num_projections", "Number of projections", "Number of project operators."),
    "algebra__n_sequence": ("algebra_num_sequences", "Number of sequences", "Number of sequence operators."),
    "algebra__n_distinct": ("query_num_distinct", "Number of DISTINCT modifiers", "Number of DISTINCT modifiers (SELECT DISTINCT)."),
    "algebra__n_slice": ("query_num_limit_offset", "Number of LIMIT / OFFSET", "Number of LIMIT / OFFSET modifiers."),
    "algebra__n_paths": ("query_num_property_paths", "Number of property paths",
                         "Number of property-path expressions (e.g. wdt:P31/wdt:P279*)."),
    "algebra__n_subqueries": ("algebra_num_inner_projections", "Number of inner projections",
                              "Number of project operators below the root of the algebra tree."),
    "algebra__max_depth": ("algebra_depth", "Algebra depth", "Depth of the Jena algebra tree."),
    "algebra__n_leaves": ("algebra_num_leaves", "Number of algebra leaves", "Number of leaves of the Jena algebra tree."),
    "algebra__max_branching_factor": ("algebra_max_branching", "Max branching factor",
                                      "Largest number of children of an algebra operator."),
    "algebra__mean_branching_factor": ("algebra_mean_branching", "Mean branching factor",
                                       "Mean number of children of the inner algebra operators."),
    "algebra__n_binary_ops": ("algebra_num_binary_ops", "Number of binary operators", "Number of algebra operators with two children."),
    "algebra__n_unary_ops": ("algebra_num_unary_ops", "Number of unary operators", "Number of algebra operators with one child."),
    "algebra__longest_unary_chain": ("algebra_unary_chain", "Longest unary chain",
                                     "Length of the longest chain of consecutive unary operators."),
    "algebra__jena_has_group_by": ("algebra_has_group_by", "Has GROUP BY", "1 if the query groups results, else 0."),
    "algebra__jena_has_having": ("query_has_having", "Has HAVING clause", "1 if the query has a HAVING clause, else 0."),
}
ENTITY = {
    "num_statements": ("num_statements", "Number of statements", "Number of statements (claims) of the entity."),
    "num_references": ("num_references", "Number of references", "Number of distinct references supporting its statements."),
    "num_properties": ("num_properties", "Number of properties", "Number of distinct properties in its statements."),
    "num_sitelinks": ("num_sitelinks", "Number of sitelinks", "Number of Wikipedia / Wikimedia articles about the entity."),
    "num_aliases": ("num_aliases", "Number of aliases", "Number of aliases (alternative labels) in all languages."),
    "num_languages": ("num_languages", "Number of label languages", "Number of languages with a label, alias or description."),
    "outgoing_degree": ("outgoing_degree", "Outgoing degree", "Number of direct (wdt:) triples with the entity as subject."),
    "incoming_degree_capped": ("incoming_degree", "Incoming degree",
                               "Number of direct (wdt:) triples with the entity as object, capped at 1,000,000."),
    "entity_entropy": ("entropy", "Entity entropy",
                       "Shannon entropy (bits) of the entity's direct triples over its properties."),
    "entity_obscurity": ("obscurity", "Entity obscurity",
                         "1 / (1 + ln(1 + sitelinks) + ln(1 + properties used)); higher = less well-known."),
}
PROPERTY = {
    "property_frequency": ("num_triples", "Number of triples", "Number of direct (wdt:) triples with the property."),
    "distinct_value_count": ("num_values", "Number of distinct values", "Number of distinct objects of the property."),
    "property_entropy": ("entropy", "Property entropy",
                         "Shannon entropy (bits) of the property's triples over its values (objects)."),
    "property_subject_count": ("num_subjects", "Number of subjects", "Number of distinct subjects of the property."),
    "property_obscurity": ("obscurity", "Property obscurity", "1 / (1 + ln(1 + subjects)); higher = more rarely used."),
}
AGG_TEXT = {"mean": "mean", "min": "minimum", "max": "maximum"}
PLURAL = {"entity": "entities", "property": "properties"}


def build_names():
    names = dict(QUERY)
    names["entity__has_entity"] = ("entity_has_entity", "Has entity", "1 if the query contains a Wikidata entity, else 0.")
    names["property__has_property"] = ("has_property", "Has property",
                                       "1 if the query contains a Wikidata property, else 0.")
    for level, fields in (("entity", ENTITY), ("property", PROPERTY)):
        for raw, (col, name, desc) in fields.items():
            for a in AGG_TEXT:
                label = name if "entropy" in name or "obscurity" in name else f"{level.capitalize()}: {name.lower()}"
                names[f"{level}__{raw}__{a}"] = (f"{level}_{col}_{a}", f"{label} ({a})",
                                                 f"{desc} {AGG_TEXT[a].capitalize()} over the {PLURAL[level]} of the query.")
    return names


NAMES = build_names()   # raw column -> (column, display name, description)
DISPLAY = {col: name for col, name, _ in NAMES.values()}

# short names for the paper table
SHORT_QUERY = {
    "query__triple_pattern_count": "Triple patterns", "query__distinct_entity_count": "Entities",
    "query__distinct_property_count": "Properties", "query__variable_count": "Variables",
    "query__optional_count": "OPTIONAL", "query__union_count": "UNION", "query__filter_count": "FILTER",
    "query__subquery_count": "Subqueries", "query__aggregation_count": "Aggregates", "query__group_by_count": "GROUP BY",
    "query__order_by_count": "ORDER BY", "query__query_chars": "Query length", "query__question_words": "Question length",
    "algebra__is_ask": "ASK query", "algebra__jena_num_variables": "Result variables", "algebra__n_extend": "BIND",
    "algebra__n_distinct": "DISTINCT", "algebra__n_slice": "LIMIT / OFFSET", "algebra__n_paths": "Property paths",
    "algebra__jena_has_having": "HAVING",
}
SHORT_FIELD = {
    "num_statements": "Statements", "num_references": "References", "num_properties": "Properties",
    "num_sitelinks": "Sitelinks", "num_aliases": "Aliases", "num_languages": "Label languages",
    "outgoing_degree": "Outgoing degree", "incoming_degree_capped": "Incoming degree",
    "entity_entropy": "Entity entropy", "entity_obscurity": "Entity obscurity", "property_frequency": "Triples",
    "distinct_value_count": "Distinct values", "property_entropy": "Property entropy",
    "property_subject_count": "Subjects", "property_obscurity": "Property obscurity",
}


def short_name(raw):
    if raw in SHORT_QUERY:
        return SHORT_QUERY[raw]
    parts = raw.split("__")
    if len(parts) == 3 and parts[1] in SHORT_FIELD:
        return SHORT_FIELD[parts[1]] + ("" if parts[2] == "mean" else f" ({parts[2]})")
    return NAMES[raw][1]


SHORT = {NAMES[raw][0]: short_name(raw) for raw in NAMES}
GROUP = {NAMES[raw][0]: ("Query" if raw.startswith(("query__", "algebra__")) else raw.split("__")[0].capitalize())
         for raw in NAMES}


TREE = "describes the Jena algebra tree"
# removed query feature -> reason
DROPPED = {
    "query__question_chars": "question length in characters (kept in words)",
    "query__query_lines": "query length in lines (kept in characters)",
    "algebra__jena_num_variables": "variables counted by Jena",
    "algebra__n_bgp": "basic graph patterns (triple patterns are counted)",
    "algebra__n_filter": "FILTER counted by Jena",
    "algebra__n_group": "aggregation counted by Jena",
    "algebra__jena_has_group_by": "GROUP BY as a 0/1 flag",
    "algebra__n_project": "one per SELECT query (ASK is counted)",
    "algebra__n_subqueries": "projections below the root, does not count subqueries",
    **{c: TREE for c in ("algebra__n_join", "algebra__n_sequence", "algebra__n_nodes", "algebra__max_depth",
                         "algebra__n_leaves", "algebra__max_branching_factor", "algebra__mean_branching_factor",
                         "algebra__n_binary_ops", "algebra__n_unary_ops", "algebra__longest_unary_chain")},
}


def group(c):
    return "Query" if c.startswith(("query__", "algebra__")) else c.split("__")[0].capitalize()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="raw features CSV (id, source_id, 86 features)")
    ap.add_argument("--output", required=True, help="reduced features CSV")
    args = ap.parse_args()

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False)   # values are copied as text
    keys = [c for c in ("id", "source_id") if c in df]
    order = {"Query": 0, "Entity": 1, "Property": 2}
    feats = sorted((c for c in df if c not in keys), key=lambda c: order[group(c)])
    unknown = [c for c in feats if c not in NAMES]
    missing = [c for c in DROPPED if c not in feats]
    if unknown or missing:
        raise SystemExit(f"unknown columns {unknown}; missing columns {missing}")

    X = df[feats].astype(float)
    removed = {c: f"constant ({X[c].iloc[0]:g})" for c in feats if X[c].nunique() == 1}
    removed.update({c: r for c, r in DROPPED.items() if c not in removed})
    kept = [c for c in feats if c not in removed and not c.endswith(("__min", "__max"))]

    with open(args.output, "w", newline="", encoding="utf-8") as f:   # same CSV format as merge_datasets.py
        w = csv.writer(f)
        w.writerow(keys + [NAMES[c][0] for c in kept])
        w.writerows(df[keys + kept].itertuples(index=False))

    print(f"{len(df):,} questions, {len(feats)} -> {len(kept)} features -> {args.output}")
    for g in order:
        print(f"  {g:8s} {sum(group(c) == g for c in feats):2d} -> {sum(group(c) == g for c in kept):2d}")
    print(f"\nRemoved ({len(removed)}, plus min / max of the entity and property statistics):")
    for c in feats:
        if c in removed:
            print(f"  {NAMES[c][1]:32s} {removed[c]}")


if __name__ == "__main__":
    main()
