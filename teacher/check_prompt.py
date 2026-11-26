"""Drift check: teacher prompts must equal what `sim.run.run_tu_do` sends. `.venv/bin/python -m teacher.check_prompt`."""
import json
import random

from core import llm
from core.scenarios import load
from sim import run as R
from teacher.helper import build_prompt


def main():
    scen, _ = load()
    rows = [json.loads(l) for l in open("data/E6/cases.jsonl")][:40]
    seen, bad = 0, 0
    for row in rows[::7]:
        case = dict(row, tai_khoan={"nhan_tai_khoan": "moi", "loai_tai_khoan": row["bang_that"]["loai_tai_khoan"],
                                    "ten_khop_tu_xung": row["bang_that"]["ten_khop_tu_xung"]})
        sent = []
        script = iter(["Họ yêu cầu gì cụ thể?", "Bạn quen họ thế nào?", "Họ có giục không?", ""])

        def fake(prompt, schema=None, model=None, image=None, **k):
            sent.append(prompt)
            return llm.Result({"du_doan": next(iter(scen)), "cau_hoi": next(script)}, "", 1, 1, 0.0, 0.0, "fake")

        def victim(c, s, h):
            return llm.Result(None, "ừ", 0, 0, 0.0, 0.0, "fake")

        orig, llm.generate = llm.generate, fake
        try:
            out = R.run_tu_do(case, scen, R.Budget(1, 0), victim_fn=victim)
        finally:
            llm.generate = orig
        hist = [{"role": "user", "text": case["tin_mo_dau"]}]
        mine = []
        for asked in range(len(sent)):
            mine.append(build_prompt(case, hist, asked, scen)[0])
            if asked < out["n_asked"]:
                hist += [{"role": "assistant", "text": out["history"][1 + 2 * asked]["text"]},
                         {"role": "user", "text": "ừ"}]
        seen += len(sent)
        bad += sum(a != b for a, b in zip(sent, mine))
    print(f"prompts compared: {seen}, different: {bad}")
    assert bad == 0


main()
