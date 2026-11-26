"""Repo-side helper for the teacher runner. Run with `.venv/bin/python -m teacher.helper` from the repo root.

The eval kernel (which owns `completion()`) cannot import the repo, so it talks to this process over JSON lines:
one request per line `{"id": .., "op": .., ...}`, one reply per line `{"id": .., "ok": true, ...}`. Requests run in
threads, replies are written under a lock. Prompts are built with the objects of `sim/run.py`, never re-typed.

Ops: "init" -> {"ids": [...], "n": 15}; "prompt" {case, history, asked}; "victim" {case, history};
"spend" -> Gemini USD so far (all runs of this brief, persisted in data/T5/gemini_spend.json).
"""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.scenarios import ROOT, load
from sim import run as R

SPEND = ROOT / "data/T5/gemini_spend.json"
CAP_USD = 1.0
_lock, _spend_lock = threading.Lock(), threading.Lock()
SCEN = None


def spend_total() -> float:
    return json.loads(SPEND.read_text())["usd"] if SPEND.exists() else 0.0


def add_spend(usd: float) -> float:
    with _spend_lock:
        tot = spend_total() + usd
        SPEND.parent.mkdir(parents=True, exist_ok=True)
        SPEND.write_text(json.dumps({"usd": round(tot, 6)}))
        return tot


def build_prompt(case: dict, history: list, asked: int, scen=None) -> tuple[str, dict]:
    """The exact prompt `run_tu_do` sends for this state, and the schema of the answer."""
    scen = scen or SCEN
    catalog = "\n".join(f"- {s.id}: {s.ten} - {s.mo_ta}" for s in scen.values())
    last = asked >= R.K
    instr = ("Đã hết lượt hỏi: chỉ đưa ra du_doan, cau_hoi để rỗng." if last else
             "Nếu đã đủ chắc thì dừng (cau_hoi rỗng), nếu chưa thì hỏi một câu giúp phân biệt các kịch bản.")
    prompt = R.FREE_PROMPT.format(catalog=catalog, chua_du=R.CHUA_DU, account=R.account_line(case), asked=asked,
                                  instruction=instr, history=R.history_text(history), image_block="")
    return prompt, R.free_schema(list(scen))


import random  # noqa: E402

from core import llm  # noqa: E402
from sim import cases as C  # noqa: E402

_tl = threading.local()
_orig_generate = llm.generate


def _generate(prompt, *a, **k):
    """Passes through, except on a thread that is capturing: then the prompt is recorded and nothing is sent."""
    if getattr(_tl, "cap", None) is not None:
        _tl.cap.append(prompt)
        return llm.Result(None, "x", 0, 0, 0.0, 0.0, "capture")
    return _orig_generate(prompt, *a, **k)


llm.generate = _generate


def capture(fn, *a):
    """The prompt `fn(*a)` (a sim function that calls llm.generate once) would send, without sending it."""
    _tl.cap = []
    try:
        fn(*a)
        return _tl.cap[0]
    finally:
        _tl.cap = None


CASE_KEYS = ("id", "kich_ban", "nhom", "tinh_cach", "viec", "bang_that", "tai_khoan", "tin_mo_dau")
TARGET = {"lua_dao": {"train": 60, "val": 10}, "binh_thuong": {"train": 90, "val": 10}}  # sessions per scenario
FLASH_SEED, CLAUDE_SEED = 20261128, 20261127  # flash-lite stories draw / make_case (T5 Part 4)


def plan(viec_path: str) -> list[dict]:
    """All Part 4 sessions in run order: round-robin over the scenarios, a seeded mix inside each scenario.
    Half of every (scenario, split) quota starts from flash-lite stories of cases_v2, half from tables drawn here."""
    viec = json.loads(Path(viec_path).read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in open(ROOT / "data/E6/cases_v2.jsonl", encoding="utf-8")]
    per = {}
    for sid in sorted(SCEN):
        nhom, mine = SCEN[sid].nhom, []
        crng = random.Random(f"{CLAUDE_SEED}:{sid}")
        i = 0
        for split in ("train", "val"):
            n = TARGET[nhom][split]
            n_claude = n // 2
            pool = [r for r in rows if r["kich_ban"] == sid and r["split"] == split]
            for r in random.Random(f"{FLASH_SEED}:{sid}:{split}").sample(pool, n - n_claude):
                c = {k: r[k] for k in CASE_KEYS if k in r}
                c["tai_khoan"] = {k: r["bang_that"][k] for k in C.KNOWN_AT_START}
                mine.append({"case": c, "split": split, "user_family": "gemini"})
            for _ in range(n_claude):
                c = C.make_case(sid, i, SCEN, crng, viec=viec[sid][i % len(viec[sid])])
                c["id"] = f"t5c_{sid}__{i}"
                mine.append({"case": c, "split": split, "user_family": "claude"})
                i += 1
        random.Random(f"{CLAUDE_SEED}:{sid}:order").shuffle(mine)
        per[sid] = mine
    order = sorted(per)
    random.Random(CLAUDE_SEED).shuffle(order)
    out = []
    for k in range(max(map(len, per.values()))):
        out += [per[s][k] for s in order if k < len(per[s])]
    return out


def handle(req: dict) -> dict:
    global SCEN
    op = req["op"]
    if op == "init":
        SCEN, issues = load()
        return {"ids": list(SCEN), "n": len(SCEN), "chua_du": R.CHUA_DU, "k": R.K, "issues": len(issues)}
    if op == "prompt":
        p, schema = build_prompt(req["case"], req["history"], req["asked"])
        return {"prompt": p, "schema": schema, "account_line": R.account_line(req["case"])}
    if op == "victim":
        if spend_total() > CAP_USD * 0.95:
            raise RuntimeError(f"Gemini cap: {spend_total():.4f} of {CAP_USD} USD")
        r = R.victim_reply(req["case"], SCEN, req["history"])
        tot = add_spend(r.usd)
        return {"text": r.text, "seconds": r.seconds, "usd": r.usd, "model": r.model, "spend": tot}
    if op == "spend":
        return {"usd": spend_total()}
    if op == "plan":
        return {"sessions": plan(req["viec_path"])}
    if op == "opening_prompt":  # the prompt `sim.cases.write_opening` would send
        return {"prompt": capture(C.write_opening, dict(req["case"]), SCEN)}
    if op == "victim_prompt":  # the prompt `victim_reply` would send; the user model is then Sonnet, not Gemini
        return {"prompt": capture(R.victim_reply, req["case"], SCEN, req["history"])}
    raise ValueError(op)


def main():
    out = sys.stdout

    def serve(line):
        req = json.loads(line)
        try:
            rep = {"id": req["id"], "ok": True, **handle(req)}
        except Exception as e:  # reported to the caller, never kills the helper
            rep = {"id": req["id"], "ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
        with _lock:
            out.write(json.dumps(rep, ensure_ascii=False) + "\n")
            out.flush()

    with ThreadPoolExecutor(16) as pool:
        for line in sys.stdin:
            if line.strip():
                pool.submit(serve, line)


if __name__ == "__main__":
    main()

