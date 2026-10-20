"""
GPT-5.4-mini 7-point judging of every model answer in the resource answers file.
"""

import argparse
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

ANSWERS = CACHE = OUT = None
EVALUATOR_MODEL = "gpt-5.4-mini-2026-03-17"

PROMPT = """
    Given the following question and correct answer, evaluate the provided model answer.

    Question: {question}
    Correct Answer: {correct_answer}
    Model Answer: {model_answer}

    Classify the model answer into one of the following categories:
    1. Perfectly Accurate (matches gold answer).
    2. Very accurate (factually correct but for different entity).
    3. Accurate but with some redundant or irrelevant information.
    4. Inaccurate (probable intrinsic error e.g from innacurate/out-of-date training data).
    5. Inaccurate (probable fabrication/hallucination).
    6. Inaccurate (irrelevant).
    7. Completely inaccurate.

    Respond with only the classification number and its label.
    """


def parse_class(text):
    m = re.match(r"^\s*([1-7])(?:[\.\):\-\s]|$)", text.strip())
    if not m:
        raise ValueError(f"Could not parse evaluator output: {text!r}")
    return int(m.group(1))


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def judge(client, row, column):
    prompt = PROMPT.format(question=row["question"], correct_answer=row["target"], model_answer=row[column])
    for attempt in range(6):
        try:
            r = client.chat.completions.create(model=EVALUATOR_MODEL, messages=[{"role": "user", "content": prompt}])
            text = r.choices[0].message.content.strip()
            return {"id": row["id"], "column": column, "evaluator_model": EVALUATOR_MODEL,
                    "evaluation": text, "class": parse_class(text)}
        except Exception as e:
            if attempt == 5:
                return {"id": row["id"], "column": column, "error": repr(e)}
            time.sleep(2 * 2 ** attempt)


def merge(rows, columns):
    cached = {c: {r["id"]: r for r in load_jsonl(CACHE / f"{c}.jsonl")} if (CACHE / f"{c}.jsonl").exists() else {}
              for c in columns}
    n = {c: 0 for c in columns}
    with open(OUT.with_suffix(".tmp"), "w", encoding="utf-8") as f:
        for row in rows:
            out = dict(row)
            for c in columns:
                e = cached[c].get(row["id"])
                out[f"eval_{c.removesuffix('-answer')}"] = (
                    {"class": e["class"], "label": e["evaluation"], "correct": int(e["class"] <= 3)} if e else None)
                n[c] += e is not None
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    OUT.with_suffix(".tmp").replace(OUT)
    return n


def main():
    global ANSWERS, CACHE, OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", required=True, help="answers JSONL (merge_datasets.py)")
    ap.add_argument("--cache-dir", default="eval_cache")
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=None, help="N random questions for n models")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--api-key-file", default=None,
                    help="file with the OpenAI API key (default: environment variable OPENAI_API_KEY)")
    args = ap.parse_args()
    ANSWERS, CACHE, OUT = Path(args.answers), Path(args.cache_dir), Path(args.output)

    rows = load_jsonl(ANSWERS)
    columns = [k for k in rows[0] if k.endswith("-answer")]
    scope = rows if args.limit is None else random.Random(args.seed).sample(rows, args.limit)
    CACHE.mkdir(parents=True, exist_ok=True)
    done = {c: {r["id"] for r in load_jsonl(CACHE / f"{c}.jsonl")} if (CACHE / f"{c}.jsonl").exists() else set()
            for c in columns}
    todo = [(r, c) for r in scope for c in columns if r["id"] not in done[c]]
    print(f"rows {len(rows)}, scope {len(scope)}, columns {columns}, to judge {len(todo)}", flush=True)

    client = None
    if todo:
        client = OpenAI(api_key=Path(args.api_key_file).read_text().strip()) if args.api_key_file else OpenAI()
    locks = {c: threading.Lock() for c in columns}
    files = {c: open(CACHE / f"{c}.jsonl", "a", encoding="utf-8") for c in columns}
    errors, t0 = 0, time.time()
    with ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(judge, client, r, c) for r, c in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            if "error" in res:
                errors += 1
                print("ERROR", res, flush=True)
                continue
            with locks[res["column"]]:
                files[res["column"]].write(json.dumps(res, ensure_ascii=False) + "\n")
                files[res["column"]].flush()
            if i % 500 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"[judge] {i}/{len(todo)} errors {errors} ({el / 60:.1f} min, ETA {(len(todo) - i) * el / i / 60:.0f} min)",
                      flush=True)
    for f in files.values():
        f.close()
    n = merge(rows, columns)
    print("judged per column:", n)
    print("Saved:", OUT)

    if args.limit is not None:
        ev = {c: {r["id"]: r for r in load_jsonl(CACHE / f"{c}.jsonl")} for c in columns}
        for r in scope:
            print("=" * 100)
            print("Q     :", r["question"])
            print("target:", r["target"])
            for c in columns:
                e = ev[c].get(r["id"])
                print(f"  {c.removesuffix('-answer'):13s} [{e['class'] if e else '-'}] {r[c][:110]!r}")


if __name__ == "__main__":
    main()
