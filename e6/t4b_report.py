"""T4b report: coherent stories (listed values only, a purpose line the opening must state).

  python3 -m e6.t4b_report pilot   -> experiments/T4b/pilot.md (spend, checks, 3 full stories per scenario)

Purpose check: an opening "carries the purpose" when it contains one of the scenario's subject words (`SUBJECT`,
whole-syllable match, with diacritics). It is a keyword proxy written by the code tab for T4b, the same kind of check
the planner ran on `data/E6/cases.jsonl`; it is applied to the old file too, for comparison. `verbatim` counts openings
that copy the purpose line word for word (diacritics and punctuation ignored).
"""
from __future__ import annotations

import collections
import json
import random
import re
import sys
import unicodedata

from core.scenarios import ROOT, load
from core.schema import FIELDS

OUT = ROOT / "experiments/T4b"
NEW_FILE, OLD_FILE = ROOT / "data/E6/cases_v2.jsonl", ROOT / "data/E6/cases.jsonl"
COST = ROOT / "data/E6/cost_v2.json"
# Spend of this brief that is not on the rows of cases_v2.json: a 30-story prompt try (not in cost_v2.json), and
# pilot A (in cost_v2.json, rows discarded). Code tab, 2026-11-26.
EXTRA_USD = {"prompt try, 6 calls, 30 stories (not kept)": 0.01204}
PILOT_A_USD = 0.10658
CAP_USD = 2.5
SUBJECT = {
    "bao_nguoi_than_cap_cuu": ["viện phí", "cấp cứu", "bệnh viện", "mổ", "tai nạn", "bị ngã", "nhập viện"],
    "bt_chuyen_cho_nguoi_than": ["bố mẹ", "ba mẹ", "sinh hoạt", "mượn", "em gái", "tiền nhà", "người nhà", "trả lại",
                                 "gửi lại"],
    "bt_dat_coc_da_xem": ["cọc", "phòng trọ", "thợ", "sửa", "xe máy", "giữ chỗ", "tiền công"],
    "bt_dat_dich_vu_co_xac_nhan": ["tour", "du lịch", "vé máy bay", "khách sạn", "đặt phòng", "khóa học", "tiếng anh",
                                   "trung tâm", "lữ hành", "đặt chỗ"],
    "bt_hoa_don_to_chuc": ["học phí", "viện phí", "tiền điện", "hóa đơn", "phí quản lý", "chung cư", "phiếu thu",
                           "tiền nước"],
    "bt_mua_online_nguoi_ban_moi": ["shop", "mua", "đơn hàng", "mỹ phẩm", "áo", "gia dụng"],
    "bt_mung_cuoi_gop_quy": ["mừng cưới", "đám cưới", "quỹ", "phúng", "viếng", "liên hoan", "họp lớp"],
    "bt_tai_khoan_cua_minh": ["của mình", "chính mình", "tiết kiệm", "chứng khoán", "đứng tên", "cá nhân", "của tôi"],
    "bt_tra_no_khoan_vay": ["trả góp", "nợ", "thẻ tín dụng", "khoản vay", "gốc", "lãi", "tài chính"],
    "bt_tra_shipper_khi_nhan_hang": ["shipper", "giao hàng", "ship", "thu hộ", "đơn hàng", "nhận hàng"],
    "bt_tra_tien_nguoi_ban_quen": ["tạp hóa", "quán", "tiền ăn", "tiền hàng", "bán hàng", "tiệm", "bữa"],
    "chuyen_nham_tien": ["nhầm", "trả lại", "hoàn lại", "hoàn trả", "tiền lạ"],
    "ctv_online": ["nhiệm vụ", "cộng tác viên", "ctv", "hoa hồng", "làm thêm"],
    "dat_coc_gia_re": ["cọc", "giữ chỗ", "giá rẻ", "combo", "vé máy bay", "khuyến mãi", "giảm giá"],
    "dau_tu_san_gia": ["đầu tư", "sàn", "tiền ảo", "lãi", "vốn", "chuyên gia"],
    "dich_vu_lay_lai_tien": ["lấy lại", "luật sư", "thu hồi", "bị mất", "đã mất"],
    "gia_co_quan_nha_nuoc": ["định danh", "lệ phí", "tiền điện", "cắt điện", "hoàn thuế", "thuế", "căn cước", "vneid"],
    "gia_cong_an": ["điều tra", "công an", "xác minh", "vụ án", "tạm giữ", "tài khoản an toàn"],
    "gia_don_hang_lon_mua_ho": ["lấy hàng", "đơn lớn", "đơn hàng lớn", "nhà cung cấp", "lô hàng", "mua giúp", "mua hộ",
                                "nhập hàng"],
    "gia_ngan_hang": ["ngân hàng", "xác minh", "hạn mức", "khóa"],
    "gia_shipper": ["shipper", "giao hàng", "giao dịch lỗi", "tổng đài", "hủy đăng ký", "đơn hàng", "tiền hàng"],
    "mao_danh_nguoi_quen": ["mượn", "sếp", "người nhà", "nhờ"],
    "mo_vi_tra_sau_nhan_hoa_hong": ["trả sau", "ứng", "vay", "giải ngân", "hoa hồng", "trả góp"],
    "tinh_cam_qua_mang_gui_qua": ["hải quan", "quà", "thông quan", "kiện hàng", "sân bay", "nước ngoài"],
    "vay_online_dong_phi_truoc": ["vay", "giải ngân"],
}
TABLE_FIELDS = ("tu_xung", "ly_do_tien", "nguoi_lien_lac", "kenh", "yeu_cau", "ap_luc")


def words(s: str, accents: bool = True) -> list[str]:
    s = unicodedata.normalize("NFC", s.lower())
    if not accents:
        s = re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFD", s.replace("đ", "d")))
    return re.findall(r"\w+", s)


def has(text: str, phrase: str, accents: bool = True) -> bool:
    return f" {' '.join(words(phrase, accents))} " in f" {' '.join(words(text, accents))} "


def purpose_hit(r: dict) -> bool:
    return any(has(r["tin_mo_dau"], w) for w in SUBJECT[r["kich_ban"]])


def verbatim(r: dict) -> bool:
    return bool(r.get("viec")) and has(r["tin_mo_dau"], r["viec"], accents=False)


def listed_ok(r: dict, scen) -> bool:
    """Every field the scenario lists holds listed values only (the account label is drawn by group, not listed)."""
    t = r["bang_that"]
    return all((set(t[n]) if FIELDS[n].multi else {t[n]}) <= set(listed)
               for n, listed in scen[r["kich_ban"]].truong.items() if n != "nhan_tai_khoan")


def read(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")] if path.exists() else []


def spend():
    c = json.loads(COST.read_text()) if COST.exists() else {"usd": 0.0, "calls": 0}
    return c, round(c["usd"] + sum(EXTRA_USD.values()), 5)


def per_scenario(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["kich_ban"]].append(r)
    return by


def story_md(r) -> list[str]:
    t = r["bang_that"]
    fields = "; ".join(f"{n} {', '.join(t[n]) if isinstance(t[n], list) else t[n]}" for n in TABLE_FIELDS)
    out = [f"- `{r['id']}` ({r['split']}, {r['tinh_cach']}, account `{t['nhan_tai_khoan']}`). Purpose line: "
           f"*{r.get('viec', '-')}*. Table: {fields}.",
           f"  - Opening: {r['tin_mo_dau']}"]
    out += [f"  - *{q}* {a}" for q, a in zip(r["cau_hoi"], r["tra_loi"])]
    return out


def pilot():
    scen, issues = load()
    assert not issues, issues
    rows, old = read(NEW_FILE), read(OLD_FILE)
    by, by_old = per_scenario(rows), per_scenario(old)
    cost, total = spend()
    n = len(rows)
    per_story = (cost["usd"] - PILOT_A_USD) / n if n else 0.0
    proj = {k: total + per_story * (25 * k - n) for k in (220, 210)}
    L = ["# T4b pilot - coherent stories\n",
         "Brief: `docs/tasks/T4b-coherent-stories.md`. Report: `python3 -m e6.t4b_report pilot`.\n",
         f"**Spend so far: {total:.4f} USD** of the {CAP_USD} USD cap (`gemini-3.5-flash-lite`; "
         f"`data/E6/cost_v2.json` {cost['usd']:.5f} USD over {cost['calls']} calls"
         + "".join(f", plus {k}: {v} USD" for k, v in EXTRA_USD.items()) + ").\n",
         "Two pilots were run. Pilot A used the brief's wording (\"in the user's own words\"): 197 of 250 openings "
         "copied the purpose line word for word, so each scenario's openings were 3-4 fixed strings (a giveaway for "
         "the classifier, and unlike real users). Those 250 rows were discarded (kept at "
         "`.cache/logs/t4b/pilot_a_cases_v2.jsonl`, spend counted above). The prompt now says: state the purpose "
         "in your own words, rephrase it, do not copy the line; and \"write Vietnamese with diacritics\" (pilot A had "
         "10 openings without diacritics, all in two scenarios). Pilot B below is the current prompt.\n",
         f"Pilot B: {n} stories, {per_story * 1000:.3f} USD per 1,000 stories. The pilot rows are cases 0-9 of the "
         f"full run and are kept. Projected total for this brief: {proj[220]:.2f} USD with 220 per scenario (200 train "
         f"+ 20 val), {proj[210]:.2f} USD with 210 (190 train + 20 val; `--n-train 190 --per-scenario 210`).\n",
         "## Checks per scenario\n",
         "Listed values: every listed field holds listed values only. Purpose (keyword proxy, see the script "
         "docstring): opening contains one of the scenario's subject words; the same proxy on the old file "
         "(`data/E6/cases.jsonl`, T4 generator) for comparison. Verbatim: opening copies the purpose line.\n",
         "| Scenario | Stories | Listed values | Purpose in opening | Old file, purpose in opening | Verbatim copy |",
         "|---|---|---|---|---|---|"]
    tot = collections.Counter()
    for s in sorted(scen):
        rs, ro = by.get(s, []), by_old.get(s, [])
        c = collections.Counter(listed=sum(listed_ok(r, scen) for r in rs), hit=sum(map(purpose_hit, rs)),
                                old=sum(map(purpose_hit, ro)), verb=sum(map(verbatim, rs)), n=len(rs), n_old=len(ro))
        tot.update(c)
        L.append(f"| `{s}` | {c['n']} | {c['listed']}/{c['n']} | {c['hit']}/{c['n']} | {c['old']}/{c['n_old']} | "
                 f"{c['verb']}/{c['n']} |")
    L.append(f"| **all** | {tot['n']} | {tot['listed']}/{tot['n']} | {tot['hit']}/{tot['n']} | "
             f"{tot['old']}/{tot['n_old']} | {tot['verb']}/{tot['n']} |\n")
    missed = [r for r in rows if not purpose_hit(r)]
    if missed:
        L.append("Openings the proxy misses (read by eye):\n")
        L += [f"- `{r['id']}` (purpose: *{r['viec']}*): {r['tin_mo_dau']}" for r in missed]
        L.append("")
    L.append("## Three full stories per scenario (seeded draw)\n")
    L.append("Drawn with `random.Random('T4b:<scenario>')`. Persona, account label, purpose line and part of the "
             "story table (given to the writer), then the opening and the three questions and answers.\n")
    for s in sorted(scen):
        L.append(f"### `{s}` ({scen[s].nhom}): {scen[s].ten}\n")
        for r in random.Random(f"T4b:{s}").sample(by.get(s, []), min(3, len(by.get(s, [])))):
            L += story_md(r)
        L.append("")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pilot.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("pilot:", (OUT / "pilot.md").relative_to(ROOT))


if __name__ == "__main__":
    {"pilot": pilot}[sys.argv[1] if len(sys.argv) > 1 else "pilot"]()
