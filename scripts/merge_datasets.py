"""
Merge everything into the release files
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

FEATURES = [
    "query__triple_pattern_count", "query__distinct_entity_count", "query__distinct_property_count",
    "query__variable_count", "query__optional_count", "query__union_count", "query__filter_count",
    "query__subquery_count", "query__aggregation_count", "query__group_by_count", "query__order_by_count",
    "query__query_chars", "query__query_lines", "query__question_chars", "query__question_words",
    "entity__has_entity",
    *[f"entity__{f}__{a}" for f in ("num_statements", "num_references", "num_properties", "num_sitelinks",
                                    "num_aliases", "num_languages", "outgoing_degree", "incoming_degree_capped",
                                    "entity_entropy", "entity_obscurity") for a in ("mean", "min", "max")],
    "property__has_property",
    *[f"property__{f}__{a}" for f in ("property_frequency", "distinct_value_count", "property_entropy",
                                      "property_subject_count", "property_obscurity") for a in ("mean", "min", "max")],
    "algebra__parse_success", "algebra__is_ask", "algebra__jena_num_variables", "algebra__n_nodes",
    "algebra__n_bgp", "algebra__n_join", "algebra__n_filter", "algebra__n_group", "algebra__n_extend",
    "algebra__n_project", "algebra__n_sequence", "algebra__n_distinct", "algebra__n_slice", "algebra__n_paths",
    "algebra__n_subqueries", "algebra__max_depth", "algebra__n_leaves", "algebra__max_branching_factor",
    "algebra__mean_branching_factor", "algebra__n_binary_ops", "algebra__n_unary_ops",
    "algebra__longest_unary_chain", "algebra__jena_has_group_by", "algebra__jena_has_having",
]
assert len(FEATURES) == 86

CHAT_PROMPT = {"system": "Answer the question directly and concisely. Do not provide explanations "
                         "or additional information unless necessary to answer the question.",
               "user": "{question}"}
RAW_PROMPT = "Question: {question}\nAnswer:"
RAW_HF = ("Hugging Face transformers, greedy decoding, max_new_tokens 128, "
          "prompt without chat template (KG-Adapter Base answers)")
RAW_VLLM = "vLLM, temperature 0, max_tokens 128, prompt without chat template"
NO_EMPTY = ("Answers empty after strip() were regenerated with Hugging Face greedy decoding "
            "and a logits processor that blocks EOS and newline-only tokens until the "
            "generated text is non-whitespace (non-empty greedy outputs are unchanged).")
VLLM_NOTE = ("vLLM and Hugging Face greedy decoding agree on short answers but can diverge "
             "late in long run-on answers (numerical differences); on a 30-question check "
             "the outputs were identical for 9/30 (Llama-3 8B) and 22/30 (Phi-4).")

ANSWER_METADATA = {
    "GPT-OSS-120B-answer": {
        "model": "openai/gpt-oss-120b", "prompt": CHAT_PROMPT,
        "generation": "vLLM (/v1/chat/completions, tensor parallel 2 over two nodes), "
                      "reasoning_effort low, max_tokens 1024, server-default sampling",
        "notes": "Missing, failed or empty answers of the first run were regenerated with "
                 "the same setup (gpt_oss_120b_fill.jsonl); empty answers re-sampled up to 5 times."},
    "LLAMA-8B-answer": {
        "model": "meta-llama/Llama-3.1-8B-Instruct", "prompt": RAW_PROMPT,
        "generation": {"valid/test": RAW_HF, "train": RAW_VLLM},
        "notes": "No train answer was empty, so none was regenerated. " + VLLM_NOTE},
    "Mistral-7B-answer": {
        "model": "mistralai/Mistral-7B-Instruct-v0.3", "prompt": RAW_PROMPT,
        "generation": {"train/valid/test": RAW_HF}, "notes": ""},
    "Phi-4-answer": {
        "model": "microsoft/phi-4", "prompt": RAW_PROMPT,
        "generation": {"valid/test": RAW_HF, "train": RAW_VLLM}, "notes": NO_EMPTY + " " + VLLM_NOTE},
    "LLAMA-70B-answer": {
        "model": "meta-llama/Llama-3.3-70B-Instruct", "prompt": CHAT_PROMPT,
        "generation": "vLLM (/v1/chat/completions, tensor parallel 2 over two nodes, bfloat16), "
                      "max_tokens 1024, the model's default sampling (temperature 0.6, top_p 0.9)",
        "notes": "Empty answers re-sampled up to 5 times (none were needed); answers that "
                 "reached max_tokens are kept truncated."},
}


def read_records(path):
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text) if text.lstrip().startswith("[") else [json.loads(l) for l in text.split("\n") if l.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def source_id(dataset_id):
    """wdql_train_189162 -> train_189162 (the WDQL id); WikiWebQuestions ids are unchanged."""
    return dataset_id[len("wdql_"):] if dataset_id.startswith("wdql_") else dataset_id


def provenance(record, source):
    gen = record.get("generation") or {}
    usage = record.get("usage") or {}
    return {"source_file": source,
            "engine": gen.get("engine") or ("vllm" if "endpoint" in gen else None),
            "no_empty_fix": bool(gen.get("no_empty_start", False)),
            "finish_reason": record.get("finish_reason"),
            "completion_tokens": usage.get("completion_tokens"),
            "attempts": record.get("attempts"),
            "generated_utc": record.get("generated_utc")}


def answer_records(path, source):

    if Path(path).suffix == ".jsonl":
        for r in read_records(path):
            if r.get("status", "OK") == "OK":
                yield r["id"], r.get("answer"), provenance(r, source)
        return
    prov = {**provenance({}, source), "engine": "hf"}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for r in (data["results"] if isinstance(data, dict) else data):
        yield r["id"], (r["evaluations"]["base"]["model_answer"] if isinstance(data, dict) else r["base"]), prov


def load_answers(paths, root):
    answers = {}
    for p in paths:
        src = str(Path(p).resolve().relative_to(root)) if Path(p).resolve().is_relative_to(root) else str(p)
        for i, ans, prov in answer_records(p, src):
            if ans is not None and str(ans).strip():
                answers[source_id(i)] = (ans, prov)
    return answers


def load_features(paths):
    feats = {}
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                feats.setdefault(r["id"], {}).update({k: v for k, v in r.items() if k != "id"})
    return feats


def write_checksums(out):
    names = sorted(p.name for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    with open(out / "SHA256SUMS.txt", "w", encoding="utf-8") as f:
        for n in names:
            f.write(f"{hashlib.sha256((out / n).read_bytes()).hexdigest()}  {n}\n")
    print("SHA256SUMS.txt:", len(names), "files")


def main():
    if sys.argv[1:2] == ["checksums"]:
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        ap.add_argument("--output-dir", required=True)
        write_checksums(Path(ap.parse_args().output_dir))
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", nargs="+", required=True, help="JSON/JSONL question files, in release order")
    ap.add_argument("--features", nargs="+", required=True, help="CSV outputs of features_wikidata.py, features_jena.py")
    ap.add_argument("--answers", action="append", default=[], help='"<MODEL>-answer=file1,file2,..." (repeatable)')
    ap.add_argument("--root", default=".", help="answer source paths are recorded relative to this directory")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(args.root).resolve()

    rows = [{k: v for k, v in r.items() if k != "split"} for p in args.dataset for r in read_records(p)]
    assert len({r["id"] for r in rows}) == len(rows), "duplicate question ids"
    write_jsonl(out / "dataset_14729.jsonl", rows)
    print(f"dataset_14729.jsonl: {len(rows):,} questions")

    feats = load_features(args.features)
    missing = [r["id"] for r in rows if r["id"] not in feats or any(c not in feats[r["id"]] for c in FEATURES)]
    if missing:
        sys.exit(f"{len(missing)} questions without all 86 features, e.g. {missing[:5]}")
    with open(out / "features_14729.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "source_id"] + FEATURES)
        for r in rows:
            w.writerow([r["id"], source_id(r["id"])] + [feats[r["id"]][c] for c in FEATURES])
    print(f"features_14729.csv: {len(rows):,} rows, {len(FEATURES)} features")

    files = {}
    for a in args.answers:
        col, sep, paths = a.partition("=")
        if not sep:
            sys.exit(f'--answers expects "<MODEL>-answer=file1,file2,...", got: {a}')
        files[col] = [p for p in paths.split(",") if p]
    loaded = {c: load_answers(ps, root) for c, ps in files.items()}
    ans_rows, prov_rows, counts = [], [], dict.fromkeys(files, 0)
    for r in rows:
        a = {"id": r["id"], "question": r["question"], "gold": r["gold"], "target": r["target"]}
        p = {"id": r["id"]}
        for c, answers in loaded.items():
            a[c], p[c] = answers.get(source_id(r["id"]), ("", None))
            counts[c] += bool(a[c])
        ans_rows.append(a)
        prov_rows.append(p)
    write_jsonl(out / "answers_14729.jsonl", ans_rows)
    write_jsonl(out / "answers_provenance_14729.jsonl", prov_rows)
    meta = {}
    for c, ps in files.items():
        srcs = [str(Path(p).resolve().relative_to(root)) if Path(p).resolve().is_relative_to(root) else p for p in ps]
        meta[c] = {**ANSWER_METADATA.get(c, {}), "source_files": srcs,
                   "non_empty": {"total": counts[c], "of": len(rows)}}
    (out / "answers_metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in files:
        print(f"{c:22s}: {counts[c]:,}/{len(rows):,} answers")
    write_checksums(out)


if __name__ == "__main__":
    main()
