## Data (`data/`)

| File | Content |
|---|---|
| `dataset_14729.jsonl` | `id`, `split`, `question`, `gold` (answer list), `target` (answer string), `triples` (Wikidata triples of the question), `no_evidence`, `counterfactual` |
| `answers_14729.jsonl` | dataset fields plus one answer per model (`<MODEL>-answer`) |
| `answers_eval_14729.jsonl` | answers plus the judgments of GPT-5.4-mini (`eval_<MODEL>`) and Claude Haiku 5.5 (`claude_eval_<MODEL>`): judge class (1–7), label and `correct` (1 for classes 1–3) |
| `features_14729.csv` | features of each question (`id`, `source_id`, features) |
| `feature_correlations.csv`, `.tex` | Spearman correlation of each feature with answer correctness |
| `question_domains_14729.json` | `id`, `question`, `sparql`, the properties of the query with their domains, and `query_domain` (domain of the question) |

Answering models: GPT-OSS-120B, Llama-3.1-8B-Instruct, Mistral-7B-Instruct-v0.3, Phi-4 and
Llama-3.3-70B-Instruct. Answers were judged by GPT-5.4-mini and Claude Haiku 5.5 with the same
prompt on a 7-point scale:

1. Perfectly accurate
2. Very accurate (correct, but for a different entity)
3. Accurate with redundant or irrelevant information
4. Inaccurate (probable intrinsic error, e.g. outdated training data)
5. Inaccurate (probable fabrication / hallucination)
6. Inaccurate (irrelevant)
7. Completely inaccurate
