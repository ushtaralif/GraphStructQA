# Dataset Generation Pipeline

Scripts used to construct and analyse GraphStructQA. These are provided for the resource creators and users interested in inspecting, reproducing, or adapting the pipeline. **They are not required for ordinary use of the resource.**

To extract features for your own SPARQL queries, see [`../sparql_to_features.py`](../sparql_to_features.py) and the [source README](../README.md).

## Pipeline steps

| Step | Script | Output |
|---|---|---|
| 1 | `features_wikidata.py` | Query-text and Wikidata features per question, using a QLever endpoint. |
| 2 | `features_jena.py` | Features from the parsed query and its algebra. Java code is embedded; requires Apache Jena 6.2.0 and Java 21. |
| 3 | `generate_answers.py` | Answers from one LLM: raw prompting via Hugging Face or vLLM, or chat via vLLM. |
| 4 | `merge_datasets.py` | Release files: dataset, features (`features_14729.csv`), and answers. |
| 5 | `evaluate_answers.py` | GPT-5.4-mini judgments using the seven-category rubric (`answers_eval_14729.jsonl`). |
| 6 | `evaluate_answers_claude.py` | Claude Haiku 5.5 judgments using the same rubric and prompt, added to `answers_eval_14729.jsonl`. |
| 7 | `plot_accuracy.py` | Judge-score plots (`judge_7point.{pdf,png}`). |
| 8 | `feature_correlations.py` | Correlations between features and answer correctness (`feature_correlations.{csv,tex}`). |
| 9 | `sparql_domain_classifier.py` | Question domains inferred from SPARQL properties (`question_domains_14729.json`). Property domains are supplied by `property_classifier.py`, using Wikidata labels and descriptions. |
| 10 | `plot_domain_accuracy.py` | Accuracy per domain and model for both judges (`accuracy_by_domain.{pdf,png,csv}`). |

## Example commands

Each script documents its options through `--help`. The following Bash commands illustrate the workflow; adjust paths and replace placeholders as needed. Hugging Face and vLLM/chat generation are alternative examples.

```bash
# Input contains id, question, and sparql for WDQL and WikiWebQuestions.
Q=final_cleaned_dataset.json

python features_wikidata.py \
    --input "$Q" --ids-from dataset_14729.jsonl \
    --endpoint <QLever-endpoint> --output features_wikidata.csv

python features_jena.py \
    --input "$Q" --ids-from dataset_14729.jsonl \
    --jena-home "$JENA_HOME" --output features_jena.csv

python generate_answers.py \
    --dataset dataset_14729.jsonl --mode raw --engine hf \
    --hf-model <model> --output answers_<model>.jsonl

python generate_answers.py \
    --dataset dataset_14729.jsonl --mode chat \
    --served-model <name> --url <vLLM-server> \
    --output answers_<model>.jsonl

python merge_datasets.py \
    --dataset train.json valid.json test.json \
    --features features_wikidata.csv features_jena.csv \
    --answers "<MODEL>-answer=answers_<model>.jsonl" ... \
    --output-dir release

python evaluate_answers.py \
    --answers release/answers_14729.jsonl \
    --output release/answers_eval_14729.jsonl

python evaluate_answers_claude.py \
    --answers release/answers_eval_14729.jsonl \
    --api-key-file <key-file> \
    --output release/answers_eval_14729.jsonl

python merge_datasets.py checksums --output-dir release

python plot_accuracy.py \
    --input release/answers_eval_14729.jsonl --output-dir figures

python feature_correlations.py \
    --features release/features_14729.csv \
    --eval release/answers_eval_14729.jsonl \
    --output release/feature_correlations.csv \
    --latex release/feature_correlations.tex

python sparql_domain_classifier.py \
    --input "$Q" --output release/question_domains_14729.json

python plot_domain_accuracy.py \
    --answers release/answers_eval_14729.jsonl \
    --domains release/question_domains_14729.json \
    --output-dir figures
```

## Requirements

Requirements depend on the scripts being used:

- Python 3.12 with `numpy`, `pandas`, `matplotlib`, `requests`, `openai`, and `anthropic`.
- `torch` and `transformers` for Hugging Face generation.
- A QLever Wikidata endpoint for Wikidata feature extraction.
- Apache Jena 6.2.0 and Java 21 for parsed-query and algebra features.
- A vLLM server for vLLM or chat generation.
- `OPENAI_API_KEY` for GPT judging.
- An Anthropic API key file for Claude judging.