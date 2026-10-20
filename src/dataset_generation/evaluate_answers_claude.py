"""
Claude Haiku-5.5 with  7-point prompt
"""

import argparse
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_answers import PROMPT, load_jsonl, parse_class

MAX_TOKENS = 8000


def answer_text(message):
    return "".join(b.text for b in message.content if b.type == "text").strip()


def params(model, effort, content):
    p = {"model": model, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": content}]}
    if effort == "off":
        p["thinking"] = {"type": "disabled"}
    else:
        p["output_config"] = {"effort": effort}
    return p


def prompt_for(row, column):
    return PROMPT.format(question=row["question"], correct_answer=row["target"], model_answer=row[column])


def claude_class(text):
    t = text.replace("**", "").strip()
    try:
        return parse_class(t.lstrip("*# "))
    except ValueError:
        for line in reversed(t.splitlines()):
            if re.match(r"^\s*[1-7](?:[\.\):\-\s]|$)", line.lstrip("*# ")):
                return parse_class(line.lstrip("*# "))
        raise


def record(row_id, column, model, text):
    return {"id": row_id, "column": column, "evaluator_model": model, "evaluation": text,
            "class": claude_class(text)}


def judge(client, model, effort, row, column):
    for attempt in range(6):
        try:
            r = client.messages.create(**params(model, effort, prompt_for(row, column)))
            return record(row["id"], column, model, answer_text(r))
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError):
            raise
        except Exception as e:
            if attempt == 5:
                return {"id": row["id"], "column": column, "error": repr(e)}
            time.sleep(2 * 2 ** attempt)


def run_sync(client, model, effort, todo, cache, workers):
    locks, files, errors = {}, {}, 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(judge, client, model, effort, r, c) for r, c in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            if "error" in res:
                errors += 1
                print("ERROR", res, flush=True)
                continue
            c = res["column"]
            lock = locks.setdefault(c, threading.Lock())
            with lock:
                f = files.setdefault(c, open(cache / f"{c}.jsonl", "a", encoding="utf-8"))
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
            if i % 500 == 0 or i == len(todo):
                print(f"[judge] {i:,}/{len(todo):,} errors {errors}", flush=True)
    for f in files.values():
        f.close()


def run_batch(client, model, effort, todo, cache):
    state_path = cache / "batch.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        keys = [[r["id"], c] for r, c in todo]
        reqs = [{"custom_id": f"r{i}", "params": params(model, effort, prompt_for(r, c))}
                for i, (r, c) in enumerate(todo)]
        batch = client.messages.batches.create(requests=reqs)
        state = {"batch_id": batch.id, "keys": keys}
        state_path.write_text(json.dumps(state))
        print(f"batch {batch.id} created with {len(reqs):,} requests", flush=True)
    while True:
        b = client.messages.batches.retrieve(state["batch_id"])
        print(f"[batch] {b.processing_status} {b.request_counts}", flush=True)
        if b.processing_status == "ended":
            break
        time.sleep(120)
    files, failed = {}, 0
    for res in client.messages.batches.results(state["batch_id"]):
        row_id, c = state["keys"][int(res.custom_id[1:])]
        try:
            if res.result.type != "succeeded":
                raise RuntimeError(res.result.type)
            rec = record(row_id, c, model, answer_text(res.result.message))
        except Exception as e:
            failed += 1
            print("FAILED", row_id, c, repr(e), flush=True)
            continue
        f = files.setdefault(c, open(cache / f"{c}.jsonl", "a", encoding="utf-8"))
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    for f in files.values():
        f.close()
    state_path.rename(cache / f"batch_{state['batch_id']}_done.json")
    print(f"[batch] results written; {failed} failed (rerun to retry them)", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", required=True, help="file_to_be_evaluated")
    ap.add_argument("--api-key-file", required=True)
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--cache-dir", default="claude_eval_cache")
    ap.add_argument("--output", required=True)
    ap.add_argument("--mode", choices=["sync", "batch"], default="sync")
    ap.add_argument("--limit", type=int, default=None, help="pilot: N random questions for n models")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--effort", choices=["low", "medium", "high", "off"], default="medium",
                    help="more thinking effort more tokens")
    args = ap.parse_args()

    rows = load_jsonl(args.answers)
    columns = [k for k in rows[0] if k.endswith("-answer")]
    scope = rows if args.limit is None else random.Random(args.seed).sample(rows, args.limit)
    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    def cached():
        return {c: {r["id"]: r for r in load_jsonl(cache / f"{c}.jsonl")} if (cache / f"{c}.jsonl").exists() else {}
                for c in columns}

    done = cached()
    todo = [(r, c) for r in scope for c in columns if r["id"] not in done[c]]
    print(f"rows {len(rows):,}, scope {len(scope):,}, columns {columns}, to judge {len(todo):,}", flush=True)
    if todo or (cache / "batch.json").exists():
        key = Path(args.api_key_file).read_text(encoding="utf-8-sig").strip()
        client = anthropic.Anthropic(api_key=key)
        if args.mode == "sync":
            run_sync(client, args.model, args.effort, todo, cache, args.workers)
        else:
            run_batch(client, args.model, args.effort, todo, cache)

    done = cached()
    n = dict.fromkeys(columns, 0)
    tmp = Path(args.output).with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for row in rows:
            out = dict(row)
            for c in columns:
                e = done[c].get(row["id"])
                out[f"claude_eval_{c.removesuffix('-answer')}"] = (
                    {"class": e["class"], "label": e["evaluation"], "correct": int(e["class"] <= 3)} if e else None)
                n[c] += e is not None
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    tmp.replace(args.output)
    print("judged per column:", n)
    print("Saved:", args.output)


if __name__ == "__main__":
    main()
