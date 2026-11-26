"""Test cases (T1 part 5, E5): text only, saved under sim/cases/ so reruns are identical.

Each case: scenario id (answer key), the true story table (sampled from the scenario's own table as in part 1, fixed
seed), a persona (rushed / trusting / suspicious / rambling; "coached" is kept for E4), the user's opening message
(written once by the model, then frozen in the file) and the account facts the lookup would give.

Cases 0-4 of each scenario are the E2 set (`v1`, seed 20261121). E5 adds cases 5-19 with a new seed (20261122), drawn
the same way. These 300 cases are an evaluation set only: never train on them (E6 makes its own training cases).

The 300 files are the frozen v1 record (15 scenarios). Since catalogue v2 (T4), `make_case` draws the account label by
group and redraws ordinary tables with a scam-type detail; since T4b it draws only listed values and adds a purpose line
(`viec`). It no longer reproduces these files; `main` skips the scenarios that have no file here, so the 10 v2
scenarios never enter this set.

  python -m sim.cases            # writes missing files of the v1 scenarios only
"""
from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor

import yaml

from core import llm
from core.infer import presence, single_dist
from core.scenarios import ROOT, load
from core.schema import FIELDS

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
# T4b: what the user believes the transfer is for, 3-4 lines per scenario (simulation input only, never shown to the
# assistant). make_case draws one per case.
VIEC = yaml.safe_load((ROOT / "sim/viec_dang_lam.yaml").read_text(encoding="utf-8"))


def sample_table(s, rng: random.Random) -> dict:
    """One story table drawn from the values the scenario lists (T4b): a listed single-choice field draws among its
    listed values (probabilities renormalised), a listed multi-choice field can only hold listed values, each with its
    listed probability. A field the scenario does not list keeps the smoothed draw of `sim.perfect.sample_table`
    (`core.infer` smoothing, which inference keeps). An empty multi-choice draw means unknown."""
    t = {}
    for name, f in FIELDS.items():
        listed = s.truong.get(name)
        if f.multi:
            t[name] = [v for v, p in (listed or presence(s, name)).items() if rng.random() < p]
        else:
            d = listed or single_dist(s, name)
            t[name] = rng.choices(list(d), weights=list(d.values()))[0]
    return t


def story_text(table: dict, viec: str | None = None) -> str:
    """The true story as plain lines for the simulated user (not shown to the assistant). `viec` (T4b) is the first
    line; cases without it (v1) give the same text as before."""
    lines = [f"- Việc bạn đang làm: {viec}"] if viec else []
    for n, f in FIELDS.items():
        if n in KNOWN_AT_START or n == "mau_thuan_loi_ke_va_anh":
            continue
        v = table[n]
        if f.multi:
            v = ", ".join(v) if v else "không có / không rõ"
        lines.append(f"- {f.label}: {v}")
    return "\n".join(lines)


PURPOSE_RULE = (" Phải nói rõ việc bạn đang làm (dòng đầu của câu chuyện) nhưng bằng lời của bạn: đổi cách nói, không chép "
                "nguyên văn dòng đó; tính cách có thể nói ngắn lại nhưng không được bỏ; ngoài việc đó chỉ kể 1-3 chi tiết "
                "khác.")
OPENING_PROMPT = """Bạn đóng vai một người dùng ví điện tử sắp chuyển tiền. Một trợ lý vừa hỏi: "Bạn đang chuyển khoản \
này vì việc gì?". Viết câu trả lời đầu tiên của bạn (1-2 câu, giọng nói thường ngày) theo đúng câu chuyện và tính cách dưới \
đây. Chỉ kể 1-3 chi tiết, không kể hết.{purpose} Không dùng tên gọi của tình huống{no_scam}. Câu chuyện có thể là chuyện \
bình thường.

Tình huống chung (để hiểu bối cảnh, không chép lại): {mo_ta}
Câu chuyện thật của bạn (giá trị "khac" nghĩa là chuyện khác hẳn các lựa chọn, tự nghĩ một chi tiết hợp lý):
{story}
Tính cách: {persona}
Chỉ trả về câu trả lời."""


# Catalogue v2 (T4): the account label is drawn by group, not from the scenario table (the computed core must not
# start scoring it), and only from labels that open the chat.
ACCOUNT_LABEL = {"binh_thuong": {"moi": 0.9, "dang_bi_bao_cao": 0.1},
                 "lua_dao": {"moi": 0.6, "dang_bi_bao_cao": 0.25, "da_xac_nhan": 0.15}}
# Scam-type details an ordinary story must not carry (data plan v2, section 3.7).
SCAM_DETAIL = {"yeu_cau": {"cai_app", "doc_otp", "nap_them_de_rut"},
               "ly_do_tien": {"nhiem_vu", "dau_tu", "tai_khoan_an_toan", "khac_phuc_loi", "hoan_tien",
                              "tien_vay_chuyen_di"},
               "duoc_dan_cach_tra_loi": {"co"},
               "ap_luc": {"doa", "giu_bi_mat"}}
MAX_REDRAW = 1000


def scam_details(table: dict) -> list[str]:
    """`field=value` for every scam-type detail in a story table; an ordinary table must have none."""
    out = []
    for name, bad in SCAM_DETAIL.items():
        v = table.get(name)
        out += [f"{name}={x}" for x in (v if isinstance(v, list) else [v]) if x in bad]
    return out


def make_case(sid: str, i: int, scen, rng: random.Random) -> dict:
    """Table from the listed values; ordinary scenarios: redrawn while it carries a scam-type detail (scam scenarios:
    no redraw); account label by group; purpose line `viec` from sim/viec_dang_lam.yaml."""
    nhom = scen[sid].nhom
    truth = sample_table(scen[sid], rng)
    for _ in range(MAX_REDRAW):
        if nhom != "binh_thuong" or not scam_details(truth):
            break
        truth = sample_table(scen[sid], rng)
    else:
        raise RuntimeError(f"{sid}: no ordinary table without a scam-type detail in {MAX_REDRAW} draws")
    labels = ACCOUNT_LABEL[nhom]
    truth["nhan_tai_khoan"] = rng.choices(list(labels), weights=list(labels.values()))[0]
    viec = rng.choice(VIEC[sid])
    persona = list(PERSONAS)[i % len(PERSONAS)]
    return {"id": f"{sid}__{i}", "kich_ban": sid, "nhom": nhom, "tinh_cach": persona, "viec": viec,
            "bang_that": truth, "tai_khoan": {k: truth[k] for k in KNOWN_AT_START}, "tin_mo_dau": None}


def write_opening(case: dict, scen) -> dict:
    s = scen[case["kich_ban"]]
    viec = case.get("viec")
    p = OPENING_PROMPT.format(mo_ta=s.mo_ta, story=story_text(case["bang_that"], viec),
                              persona=PERSONAS[case["tinh_cach"]], purpose=PURPOSE_RULE if viec else "",
                              no_scam="" if case["tinh_cach"] == "nghi_ngo" else ' và từ "lừa đảo"')
    r = llm.generate(p)
    case["tin_mo_dau"] = " ".join(r.text.strip().strip('"').split())
    case["sinh_boi"] = {"model": r.model, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "usd": r.usd}
    return case


def main():
    scen, issues = load()
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    todo = []
    for sid in sorted(s for s in scen if any(CASE_DIR.glob(f"{s}__*.json"))):
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
