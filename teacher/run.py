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
# Part 6: the tier to call (None = default tier) and the suffix the resolved model id must end with (None = no check,
# Parts 2-5). A call that resolves to another id is retried and counted in WRONG_MODEL, never kept.
TEACHER_TIER = None
REQUIRE_MODEL = None
WRONG_MODEL = []


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
    """Build `tai_khoan` from `bang_that`. cases_v2 rows already carry `nhan_tai_khoan`; older E6 rows get a label
    drawn with the T4 rule, seeded by the story id."""
    t = row["bang_that"]
    labels = ACCOUNT_LABEL[row["nhom"]]
    label = t.get("nhan_tai_khoan") or random.Random(f"T5-account:{row['id']}").choices(
        list(labels), weights=list(labels.values()))[0]
    case = dict(row)
    case["bang_that"] = dict(t, nhan_tai_khoan=label)
    case["tai_khoan"] = {"nhan_tai_khoan": label, "loai_tai_khoan": t["loai_tai_khoan"],
                         "ten_khop_tu_xung": t["ten_khop_tu_xung"]}
    return case


def ask_teacher(prompt, schema, ids, retries=5):
    """One `completion()` call; returns (parsed_json, seconds, attempts, model). Retries on an error or an invalid
    answer. `model` is the id the call resolved to (`handle.attempts`), e.g. "anthropic/claude-opus-5-5"."""
    last = ""
    for attempt in range(1, retries + 1):
        t0 = time.perf_counter()
        try:
            hd = completion(prompt, schema=schema, model=TEACHER_TIER) if TEACHER_TIER else \
                completion(prompt, schema=schema)  # kernel helper, subscription model
            o = hd.wait()
            last_attempt = (getattr(hd, "attempts", None) or [{}])[-1]
            model = last_attempt.get("model")
            if last_attempt.get("effort"):
                model = f"{model}:{last_attempt['effort']}"  # effort kept with the id, e.g. "...opus-5-5:medium"
            if REQUIRE_MODEL and not (model or "").split(":")[0].endswith(REQUIRE_MODEL):
                WRONG_MODEL.append(model)
                last = f"wrong model: {model}"
                continue
            dt = time.perf_counter() - t0
            if isinstance(o, str):
                o = json.loads(o)
            if o.get("du_doan") in ids and isinstance(o.get("cau_hoi"), str):
                return {"du_doan": o["du_doan"], "cau_hoi": o["cau_hoi"].strip()}, round(dt, 2), attempt, model
            last = f"invalid answer: {str(o)[:200]}"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
        time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(last)


USER_TIER = None  # Part 7: tier for the Claude simulated user ("smol" when it resolves to Sonnet 5.5)


def ask_text(prompt, retries=3):
    """One free-text `completion()` call (Claude as the simulated user); returns (text, seconds, model id)."""
    last = ""
    for attempt in range(1, retries + 1):
        t0 = time.perf_counter()
        try:
            hd = completion(prompt, model=USER_TIER) if USER_TIER else completion(prompt)
            o = hd.wait()
            text = " ".join(str(o).strip().strip('"').split())  # same cleaning as victim_reply / write_opening
            if text:
                return text, round(time.perf_counter() - t0, 2), (getattr(hd, "attempts", None) or [{}])[-1].get("model")
            last = "empty answer"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
        time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(last)


def run_session(h, case, user_family="gemini", split=None, note=None):
    """The `run_tu_do` loop. Saves every prompt exactly as sent, the JSON returned and the user's replies.
    user_family "gemini": `victim_reply` (flash-lite) plays the user. "claude": the opening is written with the
    `write_opening` prompt and the replies with the `victim_reply` prompt, both through `completion()`.
    `note` (Part 8): text appended to the standard prompt for a second, informed call made only when the blind call
    asks; its `cau_hoi` replaces the blind one. The stored prompt stays the standard one, `du_doan` the blind one."""
    ids, k = h.info["ids"] + [h.info["chua_du"]], h.info["k"]
    case = dict(case)
    if user_family == "claude" and not case.get("tin_mo_dau"):
        case["tin_mo_dau"], _, _ = ask_text(h.call("opening_prompt", case=case)["prompt"])
    history = [{"role": "user", "text": case["tin_mo_dau"]}]
    turns, asked = [], 0
    while True:
        p = h.call("prompt", case=case, history=history, asked=asked)
        out, secs, attempts, model = ask_teacher(p["prompt"], p["schema"], ids)
        turn = {"turn": asked, "prompt": p["prompt"], "account_line": p["account_line"], "response": out,
                "seconds": secs, "attempts": attempts, "model": model}
        turns.append(turn)
        if asked >= k or not out["cau_hoi"]:
            break
        if note:
            turn["blind_cau_hoi"] = out["cau_hoi"]
            for _ in range(3):  # the informed call must ask; an empty question is retried
                inf, isecs, iatt, imodel = ask_teacher(p["prompt"] + note, p["schema"], ids)
                if inf["cau_hoi"]:
                    break
            turn["informed"] = {"du_doan": inf["du_doan"], "seconds": isecs, "attempts": iatt, "model": imodel}
            if not inf["cau_hoi"]:
                raise RuntimeError("informed call returned no question 3 times")
            out["cau_hoi"] = inf["cau_hoi"]
        history.append({"role": "assistant", "text": out["cau_hoi"]})
        asked += 1
        if user_family == "claude":
            text, vs, um = ask_text(h.call("victim_prompt", case=case, history=history)["prompt"])
            turn["user_reply"] = {"text": text, "seconds": vs, "usd": 0.0, "model": um}
        else:
            v = h.call("victim", case=case, history=history, cap_total=VICTIM_CAP_TOTAL)
            turn["user_reply"] = {"text": v["text"], "seconds": v["seconds"], "usd": v["usd"], "model": v["model"]}
        history.append({"role": "user", "text": turn["user_reply"]["text"]})
    final = turns[-1]["response"]["du_doan"]
    return {"story_id": case["id"], "scenario": case["kich_ban"], "group": case["nhom"], "split": split,
            "persona": case["tinh_cach"], "viec": case.get("viec"), "user_family": user_family,
            "account_line": turns[0]["account_line"], "tai_khoan": case["tai_khoan"], "bang_that": case["bang_that"],
            "opening": case["tin_mo_dau"], "turns": turns, "n_asked": asked, "final": final,
            "correct": final == case["kich_ban"], "teacher_seconds": round(sum(t["seconds"] for t in turns), 2)}


def run_sessions(h, items, out_path, workers=4, limit=None):
    """Resumable: story ids already in `out_path` are skipped. Errors go to `<out_path>.errors`.
    `items` are case dicts (Gemini user) or plan entries {"case", "split", "user_family"} from the helper's "plan".
    `limit` caps how many new sessions are started (the plan order is round-robin, so any prefix is balanced)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    items = [i if "case" in i else {"case": i, "split": None, "user_family": "gemini"} for i in items]
    done = {json.loads(l)["story_id"] for l in out.read_text().splitlines()} if out.exists() else set()
    todo = [i for i in items if i["case"]["id"] not in done][:limit]
    wlock, results, errors = threading.Lock(), [], []

    def one(i):
        c = i["case"]
        try:
            s = run_session(h, c, i["user_family"], i["split"], i.get("note"))
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
    return {"skipped": len(done), "ran": len(results), "errors": errors,
            "wall_seconds": round(time.perf_counter() - t0, 1), "sessions": results}


VICTIM_CAP_TOTAL = None  # Part 5 sets a ceiling on the running Gemini total (helper op "victim" cap_total)
CHUA_DU_OK = {"bt_mua_online_nguoi_ban_moi"}  # the scenario whose expected answer may also be chua_du_can_cu


def keep_reason(s):
    """None if the session is kept, else why it is dropped."""
    if s["correct"] or (s["scenario"] in CHUA_DU_OK and s["final"] == "chua_du_can_cu"):
        return None
    return f"final={s['final']}"


# Part 8 note (appended to the standard prompt for the informed call). The confused scenario is the dropped session's
# wrong final answer when that is a scenario id, else the true scenario's `doi_chieu_voi`.
RECOVER_NOTE = ("\nGhi chú riêng cho lượt này, chỉ để chọn câu hỏi: kịch bản đúng là \"{true}\" ({true_ten}); "
                "nó dễ bị nhầm với \"{conf}\" ({conf_ten}). Hãy đặt một câu hỏi ngắn cho người dùng mà câu trả lời "
                "phân biệt được hai kịch bản này. Không nêu tên hay id kịch bản nào, không gợi ý câu trả lời, không "
                "để lộ bạn đang nghĩ là kịch bản nào. \"cau_hoi\" phải là câu hỏi đó, không được rỗng.")


def recover_note(s, scen):
    """The note for dropped session `s`; `scen` maps scenario id to its yaml dict (`ten`, `doi_chieu_voi`)."""
    conf = s["final"] if s["final"] in scen else scen[s["scenario"]]["doi_chieu_voi"]
    return RECOVER_NOTE.format(true=s["scenario"], true_ten=scen[s["scenario"]]["ten"], conf=conf,
                               conf_ten=scen[conf]["ten"])


def session_rows(s):
    """Training rows of one session: one per assistant turn, answer JSON compact (du_doan, cau_hoi)."""
    return [{"messages": [{"role": "user", "content": t["prompt"]},
                          {"role": "assistant", "content": json.dumps(
                              {"du_doan": t["response"]["du_doan"], "cau_hoi": t["response"]["cau_hoi"]},
                              ensure_ascii=False, separators=(",", ":"))}],
             "story_id": s["story_id"], "scenario": s["scenario"], "turn": t["turn"]} for t in s["turns"]]


def write_training_files(sessions_path, out_dir):
    """`sessions.jsonl` (everything, with `kept` and `drop_reason`), `train.jsonl`, `val.jsonl`: one row per
    assistant turn of every kept session, answer JSON compact with keys in the order du_doan, cau_hoi.
    Ordinary sessions dropped because the final answer is `chua_du_can_cu` go to `train_chua_du.jsonl` /
    `val_chua_du.jsonl` in the same row format (the planner decides later whether the student sees them)."""
    out_dir = Path(out_dir)
    sessions = [json.loads(l) for l in open(sessions_path)]
    names = ("train", "val", "train_chua_du", "val_chua_du")
    rows = {n: [] for n in names}
    for s in sessions:
        s["drop_reason"] = keep_reason(s)
        s["kept"] = s["drop_reason"] is None
        if s["kept"]:
            bucket = s["split"]
        elif s["group"] == "binh_thuong" and s["final"] == "chua_du_can_cu":
            bucket = s["split"] + "_chua_du"
        else:
            continue
        for t in s["turns"]:
            a = json.dumps({"du_doan": t["response"]["du_doan"], "cau_hoi": t["response"]["cau_hoi"]},
                           ensure_ascii=False, separators=(",", ":"))
            rows[bucket].append({"messages": [{"role": "user", "content": t["prompt"]},
                                              {"role": "assistant", "content": a}],
                                 "story_id": s["story_id"], "scenario": s["scenario"], "turn": t["turn"]})
    with open(out_dir / "sessions.jsonl", "w") as f:
        f.writelines(json.dumps(s, ensure_ascii=False) + "\n" for s in sessions)
    for n, rs in rows.items():
        with open(out_dir / f"{n}.jsonl", "w") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rs)
    return {"sessions": len(sessions), "kept": sum(s["kept"] for s in sessions),
            **{f"{n}_rows": len(rs) for n, rs in rows.items()}}
