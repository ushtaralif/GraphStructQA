| Directory / file | Purpose |
|---|---|
| `dataset_generation/` | feature extraction, answer generation, merging, judging, question domains, feature correlations and plots; see its README |
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
