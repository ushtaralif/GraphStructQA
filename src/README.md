# Source code

Most users can work directly with the published GraphStructQA dataset. To apply the resource to your own SPARQL queries, use [`sparql_to_features.py`](sparql_to_features.py), which extracts the same feature columns as the dataset.

The [`dataset_generation/`](dataset_generation/) directory contains the scripts used to construct and analyse GraphStructQA. These are provided for the resource creators and for users interested in inspecting, reproducing, or adapting that process. Running them is **not required for ordinary use of the resource**.

| File / directory | Purpose |
|---|---|
| [`sparql_to_features.py`](sparql_to_features.py) | Main user-facing tool: extract dataset-compatible features for your own SPARQL queries. |
| [`dataset_generation/`](dataset_generation/) | Optional construction and analysis scripts. See its [README](dataset_generation/README.md) for details. |

## Extract features for your own queries

`sparql_to_features.py` computes query and Wikidata structural features using the same extraction functions and feature-column list as GraphStructQA. Its CSV output contains an `id` column followed by the dataset feature columns.

This lets you connect your own queries to the resource. For example, you can:

- Use k-nearest-neighbour (kNN) search to find dataset queries with similar feature profiles and inspect the associated LLM responses and correctness judgments.
- Train logistic regression on the resource's features and correctness labels, then apply the fitted model to features extracted from your own queries.

The script extracts features; it does not perform kNN search or train prediction models.

### Requirements

- Python and the dependencies used by the imported feature-extraction modules.
- A QLever Wikidata SPARQL endpoint, supplied with `--endpoint`.
- Apache Jena 6.2.0 and Java 21. Supply the Jena installation directory with `--jena-home`, or set the `JENA_HOME` environment variable.

Keep `dataset_generation/` alongside `sparql_to_features.py`: the script imports helper modules from that directory. You do not need to run those modules directly.

Run the examples below from the repository root. Replace `QLEVER_ENDPOINT_URL` and `PATH_TO_JENA` with your endpoint and Jena installation directory.

### One query

```bash
python src/sparql_to_features.py --endpoint "QLEVER_ENDPOINT_URL" --jena-home "PATH_TO_JENA" --sparql "SELECT ?x WHERE { wd:Q42 wdt:P69 ?x }" --question "Where was Douglas Adams educated?" --output my_features.csv
```

If `--output` is omitted, the CSV is printed to standard output.

### Multiple queries

Create a JSONL file such as `my_queries.jsonl`, with one object per line and a unique `id` for each query:

```jsonl
{"id":"q1","sparql":"SELECT ?x WHERE { wd:Q42 wdt:P69 ?x }","question":"Where was Douglas Adams educated?"}
{"id":"q2","sparql":"SELECT ?x WHERE { wd:Q42 wdt:P19 ?x }","question":"Where was Douglas Adams born?"}
```

Then run:

```bash
python src/sparql_to_features.py --endpoint "QLEVER_ENDPOINT_URL" --jena-home "PATH_TO_JENA" --input my_queries.jsonl --output my_features.csv
```

JSON input is also supported. The natural-language `question` is optional, but omitting it sets the question-length feature to zero and produces a warning. Supply it when using models or similarity searches that include this feature.

### Use the features with GraphStructQA

See the [feature descriptions](../doc/features.md) for definitions. Join the resource's feature rows to the corresponding evaluation records by `id` when constructing training examples.

Use the same feature columns, in the same order, for both the resource and your own queries. Handle missing values consistently. For kNN, scale the features so that differences in units do not dominate distances. For logistic regression, fit preprocessing and the model on the training data, then reuse that fitted preprocessing for new queries.

Wikidata structural features depend on the endpoint's data snapshot. Values extracted from a different snapshot may differ from those in the published resource.

## Optional: dataset construction and analysis

[`dataset_generation/`](dataset_generation/) contains scripts for merging source datasets, extracting features, generating LLM answers, evaluating answers, classifying question domains, and producing correlations and plots.

These scripts document how the resource was built and support further investigation or reproduction. Some require intermediate files, model access, or configuration specific to the construction workflow. See the [dataset-generation README](dataset_generation/README.md) before running them.
