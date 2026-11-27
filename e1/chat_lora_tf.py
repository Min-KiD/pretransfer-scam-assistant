"""E13 teacher-forced check: does a LoRA adapter ask when its teacher asks and stop when it stops?

  python -m e1.chat_lora_tf --models local:qwen3-4b-e13-runB-e1,local:qwen3-4b-e13-runC-e1 \
      [--val data/T5/opus/val_all.jsonl] [--out experiments/E13/tf.jsonl] [--workers 8]

Each row of the val file is one teacher turn: its user message is the exact `tu_do` prompt sim.run sends at that
point of the teacher's dialogue (catalogue, account line, question count, history so far), its assistant message is
the teacher's JSON. Every row goes to each adapter through the vLLM server at $LOCAL_LLM_URL exactly as core.llm sends
a sim.e5 turn (no system message, thinking off, JSON schema of sim.run.free_schema enforced) but greedy only: no
retry, since a retry samples at 0.7. A reply that fails is recorded as an error, not retried. No Gemini call, no cost.

Output, one line per (model, row): story_id, scenario, turn, the teacher's du_doan and whether it asks, the student's
du_doan and whether it asks. Rows already in --out for a model are skipped (resumable). e6/e13_report.py tabulates it.
"""
from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import llm
from core.scenarios import load
from sim.run import free_schema

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated local:<served lora name>")
    ap.add_argument("--val", default="data/T5/opus/val_all.jsonl", help="path relative to the repo root")
    ap.add_argument("--out", default="experiments/E13/tf.jsonl")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    scen, issues = load()
    assert not issues, issues
    schema = free_schema(list(scen))
    rows = [json.loads(l) for l in open(ROOT / a.val, encoding="utf-8")]
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for l in open(out, encoding="utf-8"):
            d = json.loads(l)
            done.add((d["model"], d["story_id"], d["turn"]))
    jobs = [(m, r) for m in a.models.split(",") for r in rows if (m, r["story_id"], r["turn"]) not in done]
    print(f"{len(jobs)} generations ({len(rows)} val rows x {len(a.models.split(','))} models, {len(done)} done)",
          flush=True)
    lock = threading.Lock()
    fh = open(out, "a", encoding="utf-8")
    n = [0, 0]

    def one(job):
        m, r = job
        t = json.loads(r["messages"][1]["content"])
        rec = {"model": m, "val": a.val, "story_id": r["story_id"], "scenario": r.get("scenario"), "turn": r["turn"],
               "teacher_du_doan": t["du_doan"], "teacher_asks": bool(t["cau_hoi"].strip())}
        try:
            res = llm.generate(r["messages"][0]["content"], schema=schema, model=m, retries=0)
            o = res.output or {}
            rec.update(student_du_doan=o.get("du_doan"), student_asks=bool((o.get("cau_hoi") or "").strip()),
                       student_cau_hoi=(o.get("cau_hoi") or "").strip(), tokens_in=res.tokens_in, seconds=res.seconds)
        except llm.LLMError as e:
            rec["error"] = str(e)[:300]
        with lock:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n[0] += 1
            n[1] += "error" in rec
            if n[0] % 200 == 0 or n[0] == len(jobs):
                print(f"  {n[0]}/{len(jobs)} done, {n[1]} errors", flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, jobs))
    fh.close()


if __name__ == "__main__":
    main()
