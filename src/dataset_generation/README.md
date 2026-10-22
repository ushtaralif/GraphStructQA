# Resource pipeline

| Step | Script | Output |
|---|---|---|
| 1 | `features_wikidata.py` | query-text and Wikidata features per question (QLever endpoint) |
| 2 | `features_jena.py` | query features from the parsed query and its algebra (Java code embedded; Apache Jena 6.2.0, Java 21) |
| 3 | `generate_answers.py` | answers of one LLM (raw prompt via Hugging Face or vLLM; chat via vLLM) |
| 4 | `merge_datasets.py` | release files: dataset, features (`features_14729.csv`), answers |
| 5 | `evaluate_answers.py` | GPT-5.4-mini 7-point judgments (`answers_eval_14729.jsonl`) |
| 6 | `evaluate_answers_claude.py` | Claude Haiku 5.5 7-point judgments (second judge, same prompt), added to `answers_eval_14729.jsonl` |
| 7 | `plot_accuracy.py` | `judge_7point.{pdf,png}` |
| 8 | `feature_correlations.py` | correlation of the features with answer correctness (`feature_correlations.{csv,tex}`) |
| 9 | `sparql_domain_classifier.py` | domain of each question from the properties in its SPARQL query (`question_domains_14729.json`); property domains come from `property_classifier.py` (Wikidata labels and descriptions) |
| 10 | `plot_domain_accuracy.py` | accuracy per domain and model for both judges (`accuracy_by_domain.{pdf,png,csv}`) |

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
python evaluate_answers_claude.py --answers release/answers_eval_14729.jsonl --api-key-file <key file> \
                            --output release/answers_eval_14729.jsonl
python merge_datasets.py checksums --output-dir release
python plot_accuracy.py     --input release/answers_eval_14729.jsonl --output-dir figures
python feature_correlations.py --features release/features_14729.csv --eval release/answers_eval_14729.jsonl \
                            --output release/feature_correlations.csv --latex release/feature_correlations.tex
python sparql_domain_classifier.py --input $Q --output release/question_domains_14729.json
python plot_domain_accuracy.py --answers release/answers_eval_14729.jsonl \
                            --domains release/question_domains_14729.json --output-dir figures
```

Requirements: Python 3.12 (numpy, pandas, matplotlib, requests, openai, anthropic; torch + transformers
for Hugging Face generation), a QLever Wikidata endpoint, Apache Jena 6.2.0 with Java 21,
vLLM servers for vLLM / chat generation, `OPENAI_API_KEY` for GPT judging and an Anthropic API key
file for Claude judging.
