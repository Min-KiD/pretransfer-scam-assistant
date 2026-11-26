"""Teacher runner: the loop of `sim/run.py::run_tu_do` with the assistant call replaced by the eval kernel's
`completion()` (this tab's subscription model, no Claude API).

Drive it from the eval kernel (Python):

    %load teacher/run.py          # defines the functions below; `completion` is the kernel's helper
    h = Helper(); h.start()       # starts `.venv/bin/python -m teacher.helper` (repo code lives there)
    run_sessions(h, cases, "data/T5/smoke.jsonl", workers=5)

Everything that touches the repo (prompt text, `victim_reply`, scenarios) runs in the helper process; this file only
needs the standard library plus the kernel's `completion`. A session already in the output file is skipped.
"""
import json
import random
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path("/home/minhnv/Documents/CV/momo-techcontest/pretransfer-scam-assistant")
PY = str(REPO / ".venv/bin/python")
# Account label draw of T4 (`sim.cases.ACCOUNT_LABEL`), repeated here only for the E6 rows that have no `tai_khoan`.
ACCOUNT_LABEL = {"binh_thuong": {"moi": 0.9, "dang_bi_bao_cao": 0.1},
                 "lua_dao": {"moi": 0.6, "dang_bi_bao_cao": 0.25, "da_xac_nhan": 0.15}}


class Helper:
    """JSON-lines client of teacher/helper.py (a `.venv/bin/python` process)."""

    def __init__(self):
        self.proc, self.pending, self.n = None, {}, 0
        self.lock = threading.Lock()

    def start(self):
        self.proc = subprocess.Popen([PY, "-m", "teacher.helper"], cwd=REPO, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        self.info = self.call("init")
        return self.info

    def _read(self):
        for line in self.proc.stdout:
            rep = json.loads(line)
            ev, box = self.pending.pop(rep["id"])
            box.append(rep)
            ev.set()

    def call(self, op, **kw):
        with self.lock:
            self.n += 1
            i, ev, box = self.n, threading.Event(), []
            self.pending[i] = (ev, box)
            self.proc.stdin.write(json.dumps({"id": i, "op": op, **kw}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        ev.wait()
        rep = box[0]
        if not rep["ok"]:
            raise RuntimeError(rep["error"])
        return rep

    def stop(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)


def with_account(row):
    """E6 rows have no `tai_khoan`: build it from `bang_that`, draw the label seeded by the story id."""
    t = row["bang_that"]
    labels = ACCOUNT_LABEL[row["nhom"]]
    label = random.Random(f"T5-account:{row['id']}").choices(list(labels), weights=list(labels.values()))[0]
    case = dict(row)
    case["bang_that"] = dict(t, nhan_tai_khoan=label)
    case["tai_khoan"] = {"nhan_tai_khoan": label, "loai_tai_khoan": t["loai_tai_khoan"],
                         "ten_khop_tu_xung": t["ten_khop_tu_xung"]}
    return case


def ask_teacher(prompt, schema, ids, retries=3):
    """One `completion()` call; returns (parsed_json, seconds, attempts). Retries on an error or an invalid answer."""
    last = ""
    for attempt in range(1, retries + 1):
        t0 = time.perf_counter()
        try:
            o = completion(prompt, schema=schema).wait()  # kernel helper, subscription model
            dt = time.perf_counter() - t0
            if isinstance(o, str):
                o = json.loads(o)
            if o.get("du_doan") in ids and isinstance(o.get("cau_hoi"), str):
                return {"du_doan": o["du_doan"], "cau_hoi": o["cau_hoi"].strip()}, round(dt, 2), attempt
            last = f"invalid answer: {str(o)[:200]}"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
        time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(last)


def run_session(h, case, user_family="gemini"):
    """The `run_tu_do` loop. Saves every prompt exactly as sent, the JSON returned and the user's replies."""
    ids, k = h.info["ids"] + [h.info["chua_du"]], h.info["k"]
    history = [{"role": "user", "text": case["tin_mo_dau"]}]
    turns, asked = [], 0
    while True:
        p = h.call("prompt", case=case, history=history, asked=asked)
        out, secs, attempts = ask_teacher(p["prompt"], p["schema"], ids)
        turn = {"turn": asked, "prompt": p["prompt"], "account_line": p["account_line"], "response": out,
                "seconds": secs, "attempts": attempts}
        turns.append(turn)
        if asked >= k or not out["cau_hoi"]:
            break
        history.append({"role": "assistant", "text": out["cau_hoi"]})
        asked += 1
        v = h.call("victim", case=case, history=history)
        turn["user_reply"] = {"text": v["text"], "seconds": v["seconds"], "usd": v["usd"], "model": v["model"]}
        history.append({"role": "user", "text": v["text"]})
    return {"story_id": case["id"], "scenario": case["kich_ban"], "group": case["nhom"], "persona": case["tinh_cach"],
            "user_family": user_family, "account_line": turns[0]["account_line"], "tai_khoan": case["tai_khoan"],
            "opening": case["tin_mo_dau"], "turns": turns, "n_asked": asked,
            "final": turns[-1]["response"]["du_doan"], "correct": turns[-1]["response"]["du_doan"] == case["kich_ban"],
            "teacher_seconds": round(sum(t["seconds"] for t in turns), 2)}


def run_sessions(h, cases, out_path, workers=4):
    """Resumable: story ids already in `out_path` are skipped. Errors go to `<out_path>.errors`."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["story_id"] for l in out.read_text().splitlines()} if out.exists() else set()
    todo = [c for c in cases if c["id"] not in done]
    wlock, results, errors = threading.Lock(), [], []

    def one(c):
        try:
            s = run_session(h, c)
        except Exception as e:
            with wlock:
                errors.append((c["id"], str(e)))
                with open(str(out) + ".errors", "a") as f:
                    f.write(json.dumps({"story_id": c["id"], "error": str(e)}, ensure_ascii=False) + "\n")
            return
        with wlock:
            with open(out, "a") as f:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
            results.append(s)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, todo))
    return {"skipped": len(done), "ran": len(results), "errors": errors, "wall_seconds": round(time.perf_counter() - t0, 1),
            "sessions": results}
