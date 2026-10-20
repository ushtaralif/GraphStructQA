# Resource pipeline

| Step | Script | Output |
|---|---|---|
| 1 | `features_wikidata.py` | 61 Wikidata / query features per question (QLever endpoint) |
| 2 | `features_jena.py` | 25 Jena features per question (Java code embedded; Apache Jena 6.2.0, Java 21) |
| 3 | `generate_answers.py` | answers of one LLM (raw prompt via Hugging Face or vLLM; chat via vLLM) |
| 4 | `merge_datasets.py` | release files: dataset, raw features (86, `features_14729.csv`), answers |
| 5 | `evaluate_answers.py` | GPT-5.4-mini 7-point judgments (`answers_eval_14729.jsonl`) |
| 6 | `evaluate_answers_claude.py` | Claude Haiku 5.5 7-point judgments (alternative judge, same prompt) |
| 7 | `plot_accuracy.py` | `judge_7point.{pdf,png}` |
| 8 | `../feature_reduction/run_reduce_features.sh` | released features (35, `features_14729_reduced_mean.csv`) |
| 9 | `../feature_reduction/run_feature_correlations.sh` | correlation of the 35 features with answer correctness (CSV + LaTeX table) |

`sparql_domain_classifier.py` assigns a domain to each question from the properties in its SPARQL
query. It is not part of the release pipeline and needs `property_classifier.py`, which is not in
this repository.

Each script documents its options (`--help`). Typical run:

```bash
Q=final_cleaned_dataset.json           # id, question, sparql of all questions (WDQL + WikiWebQuestions)
python features_wikidata.py --input $Q --ids-from dataset_14729.jsonl --endpoint your-qlever-endpoint --output features_wikidata.csv
python features_jena.py     --input $Q --ids-from dataset_14729.jsonl --jena-home $JENA_HOME --output features_jena.csv
python generate_answers.py  --dataset dataset_14729.jsonl --mode raw --engine hf --hf-model <model> --output answers_<model>.jsonl
python generate_answers.py  --dataset dataset_14729.jsonl --mode chat --served-model <name> --url <vLLM server> --output answers_<model>.jsonl
python merge_datasets.py    --dataset train.json valid.json test.json --features features_wikidata.csv features_jena.csv \
                            --answers "<MODEL>-answer=answers_<model>.jsonl" ... --output-dir release
python evaluate_answers.py  --answers release/answers_14729.jsonl --output release/answers_eval_14729.jsonl
python evaluate_answers_claude.py --answers release/answers_14729.jsonl --api-key-file <key file> \
                            --output release/answers_eval_claude_14729.jsonl      # optional second judge
python merge_datasets.py checksums --output-dir release
python plot_accuracy.py     --input release/answers_eval_14729.jsonl --output-dir figures
bash ../feature_reduction/run_reduce_features.sh release/features_14729.csv
bash ../feature_reduction/run_feature_correlations.sh
```

Steps 8–9 write to `data/feature_reduction/`; step 9 reads `data/answers_eval_14729.jsonl`.
Feature reduction (step 8) removes constant features, query features that count a SPARQL construct
already counted by another feature or describe Jena's internal operator tree, and keeps the mean of
each entity / property statistic (86 → 35 features; see `../feature_reduction/reduce_features.py`).

Requirements: Python 3.12 (numpy, pandas, matplotlib, requests, openai, anthropic; torch + transformers
for Hugging Face generation), a QLever Wikidata endpoint, Apache Jena 6.2.0 with Java 21,
vLLM servers for vLLM / chat generation, `OPENAI_API_KEY` for GPT judging and an Anthropic API key
file for Claude judging.
