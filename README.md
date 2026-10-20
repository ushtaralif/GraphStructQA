# WikiStructQA

14,729 Wikidata questions with SPARQL queries, answers of five LLMs, judgments of the answers and
features of the questions, queries, entities and properties.

Questions come from WDQL (13,149) and WikiWebQuestions (1,580), split into train (11,783),
valid (1,472) and test (1,474).

## Data (`data/`)

| File | Content |
|---|---|
| `dataset_14729.jsonl` | `id`, `split`, `question`, `gold` (answer list), `target` (answer string), `triples` (Wikidata triples of the question), `no_evidence`, `counterfactual` |
| `answers_14729.jsonl` | dataset fields plus one answer per model (`<MODEL>-answer`) |
| `answers_metadata.json` | model, prompt and generation settings of each answer column |
| `answers_eval_14729.jsonl` | answers plus `eval_<MODEL>`: judge class (1–7), label and `correct` (1 for classes 1–3) |
| `features_14729.csv` | features of each question (`id`, `source_id`, features) |
| `feature_correlations.csv`, `.tex` | Spearman correlation of each feature with answer correctness |

Answering models: GPT-OSS-120B, Llama-3.1-8B-Instruct, Mistral-7B-Instruct-v0.3, Phi-4 and
Llama-3.3-70B-Instruct. Answers were judged by GPT-5.4-mini on a 7-point scale:

1. Perfectly accurate
2. Very accurate (correct, but for a different entity)
3. Accurate with redundant or irrelevant information
4. Inaccurate (probable intrinsic error, e.g. outdated training data)
5. Inaccurate (probable fabrication / hallucination)
6. Inaccurate (irrelevant)
7. Completely inaccurate

### Features

The features are in three groups:

- **Query:** counts from the question and SPARQL query, such as triple patterns, entities,
  properties, variables, OPTIONAL / FILTER / UNION clauses, aggregates, property paths, query and
  question length, and whether the query is an ASK query.
- **Entity:** Wikidata statistics of the entities in the query (statements, references,
  properties, sitelinks, aliases, label languages, incoming and outgoing degree, entropy,
  obscurity), averaged over the entities of the query.
- **Property:** Wikidata statistics of the properties in the query (triples, distinct values,
  subjects, entropy, obscurity), averaged over the properties of the query, and `has_property`.
  If a query has no property, `has_property` is 0 and the property statistics are 0.

Query features are computed from the query text and with Apache Jena, Wikidata statistics on a
QLever Wikidata endpoint (`src/dataset_generation/features_wikidata.py`, `features_jena.py`).

## Scripts (`src/`)

| Directory / file | Purpose |
|---|---|
| `dataset_generation/` | feature extraction, answer generation, merging, judging, feature correlations and plots; see its README |
| `sparql_to_features.py` | the dataset features for your own SPARQL queries |

Feature correlations:

```bash
python src/dataset_generation/feature_correlations.py --features data/features_14729.csv \
    --eval data/answers_eval_14729.jsonl --output data/feature_correlations.csv --latex data/feature_correlations.tex
```

Features for new queries (needs a QLever Wikidata endpoint and Apache Jena 6.2.0 with Java 21):

```bash
python src/sparql_to_features.py --endpoint <QLever URL> --jena-home $JENA_HOME \
    --sparql "SELECT ?x WHERE { wd:Q42 wdt:P69 ?x }" --question "Where was Douglas Adams educated?"
```

`figures/` contains the judge-score plots.
