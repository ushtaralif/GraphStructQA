# GraphStructQA data

Release files are grouped by month. `10-2026/` contains the October 2026 release; filenames do not include the record count. IDs are unchanged.

| File in `10-2026/` | Content |
|---|---|
| `dataset.jsonl` | Questions, splits, gold answers, targets, triples and existing metadata. |
| `answers.jsonl` | LLM answers. |
| `answers_eval.jsonl` | Answers and their existing GPT and Claude judgments. |
| `features.csv` | Query and Wikidata structural features. |
| `question_domains.json` | SPARQL queries, question domains and property-domain information. |

## Extract a combined file

Run from the repository root. Python standard library only; no API keys, endpoint or model access required.

```powershell
# All questions, features, domains, answers and judgments.
python data/extraction_tool.py --output combined.jsonl

# Discover exact model names.
python data/extraction_tool.py --list-models

# Selected models only.
python data/extraction_tool.py --models LLAMA-8B Mistral-7B --output selected.jsonl

# A JSON array instead of JSONL.
python data/extraction_tool.py --format json --output combined.json

# Filter by split or question ID.
python data/extraction_tool.py --split test --models Phi-4 --output test_phi.jsonl
python data/extraction_tool.py --ids wdql_train_189162 --output example.jsonl

# Require features, answers and both judgments for the selected models.
python data/extraction_tool.py --models LLAMA-8B --complete-only --output complete.jsonl

# Explicit release selection.
python data/extraction_tool.py --data-dir data/10-2026 --output october.jsonl
```

The default release is `10-2026`, resolved relative to the script, not the current directory. Use `--overwrite` to replace an existing output. Output format defaults to JSONL regardless of the filename extension. Filters can be combined. All five record files are required; the aggregate correlation files are not inputs.

## Combined record structure

Each output record keeps the dataset fields and adds:

- `sparql`: the query from `question_domains.json`.
- `source_id`: the source ID from the features file.
- `features`: numeric feature values, excluding `id` and `source_id`.
- `domain`: the domain and property-domain fields.
- `models`: one entry per selected model, containing `answer`, `eval` (the existing GPT judgment), and `claude_eval` (the existing Claude judgment).

Judgment objects retain their original `class`, `label` and `correct` fields. There are no evaluation-run IDs or histories: each model/question record has one stored answer with its existing judgments from the two judges. Entries remain keyed by the release's question IDs; distinct IDs are not collapsed merely because their SPARQL text matches. Answering models: GPT-OSS-120B, Llama-3.1-8B-Instruct, Mistral-7B-Instruct-v0.3, Phi-4 and
Llama-3.3-70B-Instruct. Answers were judged by GPT-5.4-mini and Claude Haiku 5.5 with the same
prompt on a 7-point scale:

1. Perfectly accurate
2. Very accurate (correct, but for a different entity)
3. Accurate with redundant or irrelevant information
4. Inaccurate (probable intrinsic error, e.g. outdated training data)
5. Inaccurate (probable fabrication / hallucination)
6. Inaccurate (irrelevant)
7. Completely inaccurate


Missing features, answers or judgments are retained as `null` by default. Missing numeric feature values become `null`; other numeric features become JSON numbers. The tool reports missing file-level records, rejects duplicate/unknown IDs and conflicting copied data, and leaves the release inputs unchanged. `--complete-only` removes rows missing any feature value, selected answer or either selected-model judgment.

## Licensing

Original GraphStructQA contributions are licensed under Apache 2.0. Incorporated source material retains its upstream terms, including CC BY 4.0 for WikiWebQuestions material.

See [LICENSE](../LICENSE), [CC BY 4.0](../LICENSES/CC-BY-4.0.txt), and [Third-party notices](../THIRD_PARTY_NOTICES.md). These terms also apply to extracted files.
