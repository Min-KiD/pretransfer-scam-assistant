"""Test cases (T1 part 5, E5): text only, saved under sim/cases/ so reruns are identical.

Each case: scenario id (answer key), the true story table (sampled from the scenario's own table as in part 1, fixed
seed), a persona (rushed / trusting / suspicious / rambling; "coached" is kept for E4), the user's opening message
(written once by the model, then frozen in the file) and the account facts the lookup would give.

Cases 0-4 of each scenario are the E2 set (`v1`, seed 20261121). E5 adds cases 5-19 with a new seed (20261122), drawn
the same way. These 300 cases are an evaluation set only: never train on them (E6 makes its own training cases).

  python -m sim.cases            # writes missing files only
"""
from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor

from core import llm
from core.scenarios import ROOT, load
from core.schema import FIELDS
from sim.perfect import sample_table

CASE_DIR = ROOT / "sim/cases"
SEED = 20261121
PER_SCENARIO = 5  # the v1 set
SEED_E5 = 20261122
PER_SCENARIO_E5 = 20
PERSONAS = {
    "voi": "Đang vội, muốn chuyển cho xong; trả lời cụt, ít chữ.",
    "ca_tin": "Cả tin, tin người kia là thật, kể với thiện cảm, đôi khi bênh người kia.",
    "nghi_ngo": "Đang nghi ngờ, kể kỹ, có thể hỏi lại có phải lừa đảo không.",
    "ke_lon_xon": "Kể lan man, lộn xộn thứ tự, thêm chi tiết thừa không liên quan.",
}
KNOWN_AT_START = ("nhan_tai_khoan", "loai_tai_khoan", "ten_khop_tu_xung")  # from the account lookup


def story_text(table: dict) -> str:
    """The true story as plain lines for the simulated user (not shown to the assistant)."""
    lines = []
    for n, f in FIELDS.items():
        if n in KNOWN_AT_START or n == "mau_thuan_loi_ke_va_anh":
            continue
        v = table[n]
        if f.multi:
            v = ", ".join(v) if v else "không có / không rõ"
        lines.append(f"- {f.label}: {v}")
    return "\n".join(lines)


OPENING_PROMPT = """Bạn đóng vai một người dùng ví điện tử sắp chuyển tiền. Một trợ lý vừa hỏi: "Bạn đang chuyển khoản \
này vì việc gì?". Viết câu trả lời đầu tiên của bạn (1-2 câu, giọng nói thường ngày) theo đúng câu chuyện và tính cách dưới \
đây. Chỉ kể 1-3 chi tiết, không kể hết. Không dùng tên gọi của tình huống{no_scam}. Câu chuyện có thể là chuyện bình thường.

Tình huống chung (để hiểu bối cảnh, không chép lại): {mo_ta}
Câu chuyện thật của bạn (giá trị "khac" nghĩa là chuyện khác hẳn các lựa chọn, tự nghĩ một chi tiết hợp lý):
{story}
Tính cách: {persona}
Chỉ trả về câu trả lời."""


def make_case(sid: str, i: int, scen, rng: random.Random) -> dict:
    truth = sample_table(scen[sid], rng)
    persona = list(PERSONAS)[i % len(PERSONAS)]
    return {"id": f"{sid}__{i}", "kich_ban": sid, "nhom": scen[sid].nhom, "tinh_cach": persona,
            "bang_that": truth, "tai_khoan": {k: truth[k] for k in KNOWN_AT_START}, "tin_mo_dau": None}


def write_opening(case: dict, scen) -> dict:
    s = scen[case["kich_ban"]]
    p = OPENING_PROMPT.format(mo_ta=s.mo_ta, story=story_text(case["bang_that"]), persona=PERSONAS[case["tinh_cach"]],
                              no_scam="" if case["tinh_cach"] == "nghi_ngo" else ' và từ "lừa đảo"')
    r = llm.generate(p)
    case["tin_mo_dau"] = " ".join(r.text.strip().strip('"').split())
    case["sinh_boi"] = {"model": r.model, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "usd": r.usd}
    return case


def main():
    scen, issues = load()
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    todo = []
    for sid in sorted(scen):
        rng = random.Random(f"{SEED}:{sid}:cases")
        rng5 = random.Random(f"{SEED_E5}:{sid}:cases")
        for i in range(PER_SCENARIO_E5):
            c = make_case(sid, i, scen, rng if i < PER_SCENARIO else rng5)
            if not (CASE_DIR / f"{c['id']}.json").exists():
                todo.append(c)
    with ThreadPoolExecutor(6) as ex:
        for c in ex.map(lambda c: write_opening(c, scen), todo):
            (CASE_DIR / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(list(CASE_DIR.glob("*.json")))
    print(f"{len(todo)} new cases, {n} total in {CASE_DIR.relative_to(ROOT)}; USD {llm.USAGE.usd:.4f}")
    for i in issues:
        print("Kịch bản bị bỏ:", i)


if __name__ == "__main__":
    main()
