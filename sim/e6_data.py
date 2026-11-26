"""E6 training data: user texts for the scenario classifier, written by gemini-3.5-flash-lite.

Same recipe as the E5 cases (sim/cases.py: a true story table sampled from the scenario's own table, a persona), with
new seeds, so nothing overlaps the 300 E5 evaluation cases. One model call writes FIVE cases of one scenario at once
(their tables and personas differ): for each, the opening message and the answers to three questions picked from a
fixed list of plain follow-up questions (the questions are not part of the classifier input). Batching keeps the prompt
cost low; the output tokens are what costs money.

  python -m sim.e6_data [--per-scenario 220] [--cap-usd 2]
    -> data/E6/cases.jsonl (one row per case: id, split train|val, kich_ban, nhom, tinh_cach, bang_that, tin_mo_dau,
       cau_hoi, tra_loi), data/E6/cost.json (all runs added up). Resumable: batches already written are skipped.
Cases 0-199 of each scenario are `train`, 200-219 `val`; labels are the scenario chosen at generation time.
`--cap-usd` caps the calls of this run (since T4; E6 capped the running total): no batch starts once this run's spend
plus the batches in flight could pass it.
"""
from __future__ import annotations

import argparse
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor

from core import llm
from core.scenarios import ROOT, load
from sim.cases import PERSONAS, make_case, story_text

OUT = ROOT / "data/E6"
SEED_E6 = 20261124
BATCH = 5
N_TRAIN = 200
# Plain follow-ups an assistant asks; hand-written for E6, not taken from the E5 sessions (those are the test set).
QUESTIONS = [
    "Người nhận tiền là ai, bạn quen họ thế nào?",
    "Bạn liên lạc với họ qua kênh nào: gọi điện, Zalo, Facebook hay gặp trực tiếp?",
    "Ai là người liên lạc trước, họ hay bạn?",
    "Họ có hối thúc, đe dọa, hứa hẹn gì hay bảo bạn giữ bí mật không?",
    "Họ yêu cầu bạn làm gì cụ thể?",
    "Vì sao bạn phải chuyển khoản này?",
    "Bạn đã gặp trực tiếp người nhận tiền bao giờ chưa?",
    "Trước đó bạn đã chuyển cho họ lần nào chưa?",
    "Có ai dặn trước bạn phải trả lời thế nào nếu bị hỏi không?",
    "Họ tự giới thiệu là ai?",
]
PROMPT = """Bạn viết dữ liệu mô phỏng: {n} người dùng ví điện tử khác nhau, mỗi người sắp chuyển tiền và đang trả lời \
một trợ lý. Mỗi người có câu chuyện thật và tính cách riêng (bên dưới). Với mỗi người, viết:
- tin_mo_dau: câu trả lời cho câu hỏi "Bạn đang chuyển khoản này vì việc gì?" (1-2 câu, giọng nói thường ngày, chỉ kể 1-3 \
chi tiết, không kể hết);
- tra_loi: lần lượt trả lời ba câu hỏi được ghi cho người đó (mỗi câu 1-2 câu). Điều câu chuyện không nói thì bảo không \
biết, không rõ.
Quy tắc: chỉ kể những điều có trong câu chuyện; giá trị "khac" nghĩa là chuyện khác hẳn các lựa chọn, tự nghĩ một chi tiết \
hợp lý; không dùng tên gọi của tình huống; chỉ người có tính cách "nghi ngờ" mới được nói từ "lừa đảo". Mỗi người viết một \
giọng khác nhau, không lặp câu chữ giữa các người. Câu chuyện có thể là chuyện bình thường.

Tình huống chung (để hiểu bối cảnh, không chép lại): {mo_ta}
{people}
Trả về JSON đúng {n} phần tử, theo đúng thứ tự người."""
SCHEMA = {"type": "object", "properties": {"nguoi": {"type": "array", "items": {
    "type": "object", "properties": {"tin_mo_dau": {"type": "string"},
                                     "tra_loi": {"type": "array", "items": {"type": "string"}}},
    "required": ["tin_mo_dau", "tra_loi"]}}}, "required": ["nguoi"]}


def batches(scen, per_scenario):
    """Batch k of every scenario before batch k+1, so a stop at the cap leaves every scenario with the same count."""
    per = {}
    for sid in sorted(scen):
        rng = random.Random(f"{SEED_E6}:{sid}:e6")
        qrng = random.Random(f"{SEED_E6}:{sid}:questions")
        cases = []
        for i in range(per_scenario):
            c = make_case(sid, i, scen, rng)
            c["id"] = f"e6_{sid}__{i}"
            c["split"] = "train" if i < N_TRAIN else "val"
            c["cau_hoi"] = qrng.sample(QUESTIONS, 3)
            cases.append(c)
        per[sid] = cases
    for k in range(0, per_scenario, BATCH):
        for sid, cases in per.items():
            yield sid, cases[k:k + BATCH]


def write_batch(sid, cases, scen):
    people = "\n".join(
        f"\nNgười {j + 1}:\nCâu chuyện thật:\n{story_text(c['bang_that'])}\nTính cách: {PERSONAS[c['tinh_cach']]}\n"
        f"Ba câu hỏi: " + " | ".join(c["cau_hoi"]) for j, c in enumerate(cases))
    r = llm.generate(PROMPT.format(n=len(cases), mo_ta=scen[sid].mo_ta, people=people), schema=SCHEMA, retries=3)
    got = r.output["nguoi"]
    if len(got) != len(cases):
        raise ValueError(f"{sid}: asked {len(cases)} people, got {len(got)}")
    rows = []
    for c, g in zip(cases, got):
        rows.append({**{k: c[k] for k in ("id", "split", "kich_ban", "nhom", "tinh_cach", "bang_that", "cau_hoi")},
                     "tin_mo_dau": " ".join(g["tin_mo_dau"].split()),
                     "tra_loi": [" ".join(a.split()) for a in g["tra_loi"][:3]]})
    return rows, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-scenario", type=int, default=220)
    ap.add_argument("--cap-usd", type=float, default=2.0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    scen, issues = load()
    assert not issues, issues
    OUT.mkdir(parents=True, exist_ok=True)
    path, cost_path = OUT / "cases.jsonl", OUT / "cost.json"
    done = {json.loads(l)["id"] for l in open(path, encoding="utf-8")} if path.exists() else set()
    cost = json.loads(cost_path.read_text()) if cost_path.exists() else {"model": llm.DEFAULT_MODEL, "calls": 0,
                                                                          "tokens_in": 0, "tokens_out": 0, "usd": 0.0}
    todo = [(sid, cs) for sid, cs in batches(scen, a.per_scenario) if not all(c["id"] in done for c in cs)]
    print(f"{len(todo)} batches to write; spent so far {cost['usd']:.3f} USD (earlier runs); cap for this run "
          f"{a.cap_usd} USD", flush=True)
    lock, failed = threading.Lock(), []
    base = dict(cost)  # earlier runs; every call of this run (retries and failed batches included) is in llm.USAGE

    def save():
        u = llm.USAGE
        cost.update(calls=base["calls"] + u.calls, tokens_in=base["tokens_in"] + u.tokens_in,
                    tokens_out=base["tokens_out"] + u.tokens_out, usd=round(base["usd"] + u.usd, 5))
        cost_path.write_text(json.dumps(cost, indent=1))

    def one(item):
        sid, cs = item
        u = llm.USAGE
        if u.usd + a.workers * (u.usd / u.calls if u.calls else 0) >= a.cap_usd:
            return
        try:
            rows, _ = write_batch(sid, cs, scen)
        except Exception as e:
            failed.append(f"{cs[0]['id']}: {type(e).__name__}: {str(e)[:150]}")
            with lock:
                save()
            return
        with lock:
            with open(path, "a", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            save()

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, todo))
    n = sum(1 for _ in open(path, encoding="utf-8")) if path.exists() else 0
    print(f"{n} cases in {path.relative_to(ROOT)}; this run {llm.USAGE.calls} calls, {llm.USAGE.usd:.4f} USD "
          f"(all runs {cost['usd']:.3f}); failed {len(failed)}")
    for f in failed[:10]:
        print("  ", f)


if __name__ == "__main__":
    main()
