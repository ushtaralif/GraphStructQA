"""
LLM answers for the resource questions (one model per run; resumable).
"""

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

RAW_PROMPT = "Question: {q}\nAnswer:"
RAW_MAX_NEW = 128
SYSTEM_PROMPT = ("Answer the question directly and concisely. Do not provide explanations or "
                 "additional information unless necessary to answer the question.")
CHAT_MAX_TOKENS, CHAT_MAX_TRIES = 1024, 5


def post(url, body, timeout=900):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class HF:
    def __init__(self, path):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessor, LogitsProcessorList
        self.torch, self.path = torch, path
        self.tok = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16, device_map="cuda").eval()
        tok = self.tok
        newline = [i for i in range(len(tok)) if (s := tok.decode([i])).strip() == "" and "\n" in s]
        eos = self.model.generation_config.eos_token_id
        eos = set(eos if isinstance(eos, list) else [eos]) | {tok.eos_token_id}
        bad = torch.tensor(sorted(set(newline) | eos))

        class NoEmptyStart(LogitsProcessor):
            def __init__(self, prompt_len):
                self.prompt_len = prompt_len

            def __call__(self, input_ids, scores):
                for b in range(input_ids.shape[0]):
                    if not tok.decode(input_ids[b, self.prompt_len:], skip_special_tokens=True).strip():
                        scores[b, bad.to(scores.device)] = -float("inf")
                return scores

        self.no_empty = lambda n: LogitsProcessorList([NoEmptyStart(n)])

    def answer(self, question, no_empty=False):
        x = self.tok(RAW_PROMPT.format(q=question), return_tensors="pt").to("cuda")
        n = x["input_ids"].shape[1]
        kw = {"logits_processor": self.no_empty(n)} if no_empty else {}
        with self.torch.no_grad():
            g = self.model.generate(**x, max_new_tokens=RAW_MAX_NEW, do_sample=False,
                                    pad_token_id=self.tok.eos_token_id, **kw)
        return self.tok.decode(g[0, n:], skip_special_tokens=True).strip()


def raw_hf_record(hf, row):
    ans = hf.answer(row["question"])
    fix = not ans
    if fix:
        ans = hf.answer(row["question"], no_empty=True)
    return {"id": row["id"], "question": row["question"], "answer": ans, "status": "OK",
            "generation": {"engine": "hf", "prompt": "Question: {q}\\nAnswer:", "greedy": True,
                           "max_new_tokens": RAW_MAX_NEW, "no_empty_start": fix, "model_path": hf.path}}


def raw_vllm_record(url, served, row):
    body = {"model": served, "prompt": RAW_PROMPT.format(q=row["question"]), "max_tokens": RAW_MAX_NEW,
            "temperature": 0.0}
    for attempt in range(6):
        try:
            c = post(url.rstrip("/") + "/v1/completions", body, timeout=600)["choices"][0]
            break
        except Exception as e:
            err = repr(e)
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(err)
    return {"id": row["id"], "question": row["question"], "answer": c["text"].strip(), "status": "OK",
            "finish_reason": c.get("finish_reason"),
            "generation": {"engine": "vllm", "prompt": "Question: {q}\\nAnswer:", "temperature": 0,
                           "max_tokens": RAW_MAX_NEW, "model_path": served}}


def chat_record(url, served, extra, row):
    endpoint = url.rstrip("/") + "/v1/chat/completions"
    body = {"model": served, "max_tokens": CHAT_MAX_TOKENS, **extra,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": row["question"]}]}
    rec = {"id": row["id"], "served_model": served, "question": row["question"], "answer": None, "status": "ERROR",
           "attempts": 0}
    t0 = time.time()
    for attempt in range(1, CHAT_MAX_TRIES + 1):
        rec["attempts"] = attempt
        try:
            r = post(endpoint, body)
        except Exception as e:
            rec["error"] = repr(e)
            time.sleep(5 * attempt)
            continue
        c = r["choices"][0]
        ans = (c["message"].get("content") or "").strip()
        rec.update(answer=ans, finish_reason=c.get("finish_reason"), usage=r.get("usage"), request_id=r.get("id"))
        rec.pop("error", None)
        if ans:
            rec["status"] = "OK"
            break
        rec["status"] = "EMPTY"
    rec.update(elapsed_seconds=round(time.time() - t0, 4),
               generation={"endpoint": endpoint, "system_prompt": SYSTEM_PROMPT, "max_tokens": CHAT_MAX_TOKENS,
                           **extra, "temperature": "server_default", "max_tries_if_empty": CHAT_MAX_TRIES},
               generated_utc=datetime.now(timezone.utc).isoformat())
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, help="JSONL with id, question")
    ap.add_argument("--mode", choices=["raw", "chat"], required=True)
    ap.add_argument("--engine", choices=["hf", "vllm"], default="hf", help="raw mode only")
    ap.add_argument("--hf-model", default=None, help="Hugging Face model path (raw/hf, and empty-answer fix)")
    ap.add_argument("--served-model", default=None, help="model name on the vLLM server")
    ap.add_argument("--url", default="You_Vllm_server_URL", help="vLLM server")
    ap.add_argument("--reasoning-effort", default=None, help="chat mode, e.g. low (GPT-OSS)")
    ap.add_argument("--workers", type=int, default=64, help="parallel requests (vLLM)")
    ap.add_argument("--ids", default=None, help="JSON list of ids to (re)generate")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    data = [json.loads(l) for l in open(args.dataset, encoding="utf-8") if l.strip()]
    if args.ids:
        keep = set(json.load(open(args.ids)))
        data = [r for r in data if r["id"] in keep]
    out = Path(args.output)
    done = {r["id"] for r in map(json.loads, open(out, encoding="utf-8")) if r["status"] == "OK"} if out.exists() else set()
    todo = [r for r in data if r["id"] not in done][: args.limit]
    print(f"{len(data):,} questions, {len(done):,} done, {len(todo):,} to generate", flush=True)

    hf = HF(args.hf_model) if args.hf_model and (args.mode == "raw") else None
    if args.mode == "raw" and args.engine == "hf":
        job = lambda r: raw_hf_record(hf, r)
        workers = 1
    elif args.mode == "raw":
        job = lambda r: raw_vllm_record(args.url, args.served_model, r)
        workers = args.workers
    else:
        extra = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}
        job = lambda r: chat_record(args.url, args.served_model, extra, r)
        workers = args.workers

    with open(out, "a", encoding="utf-8") as f, ThreadPoolExecutor(workers) as ex:
        for n, rec in enumerate(ex.map(job, todo), 1):
            if args.mode == "raw" and not rec["answer"]:
                if hf is None:
                    rec["status"] = "EMPTY"
                else:
                    rec = {**raw_hf_record(hf, {"id": rec["id"], "question": rec["question"]})}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if n % 200 == 0 or n == len(todo):
                f.flush()
                print(f"{n:,}/{len(todo):,}", flush=True)


if __name__ == "__main__":
    main()
