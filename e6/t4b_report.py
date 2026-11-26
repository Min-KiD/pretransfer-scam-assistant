"""T4b report: coherent stories (listed values only, plain-word values, a purpose line the opening must state) and C0
v3 trained on them -> experiments/T4b/report.md (English). Needs numpy and scikit-learn (anaconda python3).

  python3 -m e6.t4b_report

The pilot gate note (experiments/T4b/pilot.md) was written by an earlier version of this script on the pilot B rows,
which the planner then discarded.

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
import unicodedata

from core.scenarios import ROOT, load
from core.schema import FIELDS

OUT = ROOT / "experiments/T4b"
NEW_FILE, OLD_FILE = ROOT / "data/E6/cases_v2.jsonl", ROOT / "data/E6/cases.jsonl"
COST = ROOT / "data/E6/cost_v2.json"
# Spend of this brief not on the rows of cases_v2.jsonl: pilots A and B (in cost_v2.json, rows discarded, kept in
# .cache/logs/t4b/) and a 30-story prompt try (not in cost_v2.json). Code tab, 2026-11-26.
EXTRA_USD = {"prompt try, 6 calls, 30 stories (not kept)": 0.01204}
PILOTS_USD = {"A": 0.10658, "B": 0.10937}
CAP_USD = 2.75
KINDS = ("mo_dau", "day_du")
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


def no_diacritics(r: dict) -> bool:
    s = unicodedata.normalize("NFD", r["tin_mo_dau"])
    return not re.search(r"[\u0300-\u036fđĐ]", s) and bool(re.search(r"[a-zA-Z]", s))


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


def header(title, cmd, cost, total) -> list[str]:
    return [f"# {title}\n",
            f"Brief: `docs/tasks/T4b-coherent-stories.md` (with the planner's decisions after the pilot). Report: "
            f"`{cmd}`.\n",
            f"**Spend: {total:.4f} USD** of the {CAP_USD} USD cap for this brief (`gemini-3.5-flash-lite`; "
            f"`data/E6/cost_v2.json` {cost['usd']:.5f} USD over {cost['calls']} calls, which includes the two "
            f"discarded pilots ({' + '.join(f'{k} {v}' for k, v in PILOTS_USD.items())} USD)"
            + "".join(f", plus {k}: {v} USD" for k, v in EXTRA_USD.items()) + ").\n",
            "Two pilots of 250 stories were discarded (kept in `.cache/logs/t4b/`). Pilot A used the brief's wording "
            "(\"in the user's own words\"): 197 of 250 openings copied the purpose line word for word, so each "
            "scenario's openings were 3-4 fixed strings (a giveaway for the classifier, and unlike real users); 10 "
            "openings, all in two scenarios, had no diacritics. The prompt now says: state the purpose in your own "
            "words, rephrase it, do not copy the line; write Vietnamese with diacritics. Pilot B fixed that, but the "
            "story table still showed raw value ids, and 13 of the 17 users with `tu_xung: nguoi_ban` (a seller) who "
            "were asked \"Họ tự giới thiệu là ai?\" called the other side a friend or acquaintance (the id reads as "
            "\"người bạn\"). The writer now sees every value in plain Vietnamese (`sim/gia_tri_bang_loi.yaml`) and "
            "the field labels without their id glossary; the run stopped itself if that rate was 10% or more after "
            "500 stories.\n"]


def checks(scen, rows, old, max_missed=None) -> list[str]:
    by, by_old = per_scenario(rows), per_scenario(old)
    L = ["## Checks per scenario\n",
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
        shown = missed if max_missed is None else random.Random("T4b:missed").sample(missed, min(max_missed,
                                                                                               len(missed)))
        L.append(f"Openings the proxy misses: {len(missed)}"
                 + (f"; {len(shown)} drawn at random" if len(shown) < len(missed) else "") + ":\n")
        L += [f"- `{r['id']}` (purpose: *{r['viec']}*): {r['tin_mo_dau']}" for r in shown]
        L.append("")
    return L


def stories(scen, rows, k) -> list[str]:
    by = per_scenario(rows)
    L = [f"## {k} stories per scenario (seeded draw)\n",
         "Drawn with `random.Random('T4b:<scenario>')`. Persona, account label, purpose line and part of the story "
         "table (given to the writer), then the opening and the three questions and answers.\n"]
    for s in sorted(scen):
        L.append(f"### `{s}` ({scen[s].nhom}): {scen[s].ten}\n")
        rs = sorted(by.get(s, []), key=lambda r: int(r["id"].rsplit("__", 1)[1]))
        for r in random.Random(f"T4b:{s}").sample(rs, min(k, len(rs))):
            L += story_md(r)
        L.append("")
    return L


def write(name, L):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("report:", (OUT / name).relative_to(ROOT))


def main():
    """C0 v3 (trained on cases_v2.jsonl) next to C0 v2 (trained on cases.jsonl)."""
    from e6.classify import DATA, SCEN_V2, WDIR, c0_predict, train_val
    from e6.t4_report import acc, cross, load_preds, paired
    from sim.e5 import fmt, rate
    from sim.e6_data import FRIEND_WORDS, WHO_Q, friend_answers

    scen, issues = load()
    assert not issues, issues
    nhom = {s: scen[s].nhom for s in scen}
    rows, old = read(NEW_FILE), read(OLD_FILE)
    cost, total = spend()
    meta = json.loads((DATA / "v3/models.json").read_text())["c0"]
    p2 = load_preds(DATA / "v2/preds/c0.jsonl", SCEN_V2)
    p3 = load_preds(DATA / "v3/preds/c0.jsonl", SCEN_V2)
    split = collections.Counter((r["split"]) for r in rows)
    L = header("T4b - coherent stories: listed values only, purpose line; C0 v3", "python3 -m e6.t4b_report", cost,
               total)
    fk, fn = friend_answers(rows)
    L.append(f"Friend check on the whole file: users with `tu_xung: nguoi_ban` asked \"{WHO_Q}\" whose answer "
             f"contains {', '.join(repr(w) for w in FRIEND_WORDS)}: {fmt(rate(fk, fn))} (pilot B: 13/17). Openings "
             f"without any diacritic: {sum(map(no_diacritics, rows))} of {len(rows)} (the prompt asks for them).\n")
    L.append(f"Stories in `data/E6/cases_v2.jsonl`: {len(rows)} ({split['train']} train, {split['val']} val; "
             f"{len(rows) // 25} per scenario). C0 v3: TF-IDF + logistic regression on these rows, 25 labels, "
             f"C={meta['train']['C']} (grid 1, 4, 16, 64, picked on val), val macro-F1 {meta['train']['val_macro_f1']}, "
             f"{meta['train_n']} train and {meta['val_n']} val inputs (two per row), ordinary rows dropped by the "
             f"scam-detail rule: {len(meta['dropped']['train']) + len(meta['dropped']['val'])}, CPU "
             f"{meta['cpu_ms_p50']} ms per text (p50), {meta['size_mb']} MB. C0 v2 (T4) is unchanged.\n")
    L += checks(scen, rows, old, max_missed=20)

    # ---- val, own sets and crossed
    _, val2, _ = train_val("v2")
    _, val3, _ = train_val("v3")

    def crossed(model_dir, items):
        probs, _ = c0_predict([it["text"] for it in items], model_dir)
        out = []
        for it, p in zip(items, probs):
            i = max(range(len(SCEN_V2)), key=lambda j: p[j])
            out.append({"id": it["id"], "kind": it["kind"], "label": SCEN_V2[it["y"]], "top": SCEN_V2[i]})
        return out

    v2_on_3, v3_on_2 = crossed(WDIR / "v2/c0", val3), crossed(WDIR / "v3/c0", val2)
    own2 = [r for r in p2 if r["set"] == "val"]
    own3 = [r for r in p3 if r["set"] == "val"]
    lines = {(r["kich_ban"], r["viec"]) for r in rows}
    seen = {(r["kich_ban"], r["viec"]) for r in rows if r["split"] == "train"}
    v_rows = [r for r in rows if r["split"] == "val"]
    L += ["## C0 on val\n",
          "The two val sets differ: C0 v2's val is the 20 val stories per scenario of `cases.jsonl` (old generator, "
          "16 ordinary rows dropped by the rule), C0 v3's is the 20 of `cases_v2.jsonl` (listed values, purpose line). "
          "The crossed rows run each model on the other's val set, so each set is scored by both models.\n",
          f"**C0 v3's own val score is not a generalisation measure.** The stories use {len(lines)} purpose lines "
          f"(3-4 per scenario) and {sum((r['kich_ban'], r['viec']) in seen for r in v_rows)} of {len(v_rows)} val "
          "stories state a purpose line that train stories state too, in other words. The new val tells whether a "
          "story is recognised from those purposes; the old val and the real narratives below tell how far that "
          "carries.\n",
          "| Model | Val set | Input | Correct scenario | Scam called ordinary | Ordinary called scam |",
          "|---|---|---|---|---|---|"]
    for name, vs, rs in (("C0 v2", "old (`cases.jsonl`)", own2), ("C0 v3", "old (`cases.jsonl`)", v3_on_2),
                         ("C0 v2", "new (`cases_v2.jsonl`)", v2_on_3), ("C0 v3", "new (`cases_v2.jsonl`)", own3)):
        for k in KINDS:
            x = [r for r in rs if r["kind"] == k]
            L.append(f"| {name} | {vs} | `{k}` | {acc(x)} | {cross(x, nhom, 'lua_dao', 'binh_thuong')} | "
                     f"{cross(x, nhom, 'binh_thuong', 'lua_dao')} |")
    L += ["\nPer scenario, correct scenario on each model's own val set (C0 v2: old set; C0 v3: new set):\n",
          "| Scenario | Group | C0 v2 `mo_dau` | C0 v3 `mo_dau` | C0 v2 `day_du` | C0 v3 `day_du` |",
          "|---|---|---|---|---|---|"]
    for s in SCEN_V2:
        cells = [acc([r for r in rs if r["kind"] == k and r["label"] == s]) for k in KINDS for rs in (own2, own3)]
        L.append(f"| `{s}` | {nhom[s]} | " + " | ".join(cells) + " |")

    # ---- 300 v1 openings (same inputs for both models)
    L += ["\n## The openings of the 300 v1 cases\n",
          "Same 300 inputs for both models (v1 generator, 15 scenarios); paired bootstrap 95% interval, exact "
          "McNemar.\n",
          "| Model | Correct scenario | Scam called ordinary | Ordinary called scam |", "|---|---|---|---|"]
    sim2 = [r for r in p2 if r["set"] == "sim"]
    sim3 = [r for r in p3 if r["set"] == "sim"]
    for name, rs in (("C0 v2", sim2), ("C0 v3", sim3)):
        L.append(f"| {name} | {acc(rs)} | {cross(rs, nhom, 'lua_dao', 'binh_thuong')} | "
                 f"{cross(rs, nhom, 'binh_thuong', 'lua_dao')} |")
    n, k3, k2, d, lo, hi, p = paired({r["id"]: r["top"] == r["label"] for r in sim3},
                                      {r["id"]: r["top"] == r["label"] for r in sim2})
    L.append(f"\nv3 - v2: {d:+.1f} points [{lo:+.1f}, {hi:+.1f}], McNemar p={p:.3f} (n={n}).\n")

    # ---- real narratives
    narr = {p_.stem: json.loads(p_.read_text(encoding="utf-8"))
            for p_ in sorted((ROOT / "data/narr/real").glob("*.json"))}
    real = {name: [r for r in pr if r["set"] == "real" and r["label"] != "khac"] for name, pr in
            (("C0 v2", p2), ("C0 v3", p3))}
    L += ["## Real narratives (84 labelled, all scams)\n",
          "| Model | Correct scenario | Called ordinary |", "|---|---|---|"]
    for name, rs in real.items():
        L.append(f"| {name} | {acc(rs)} | {cross(rs, nhom, 'lua_dao', 'binh_thuong')} |")
    n, k3, k2, d, lo, hi, p = paired({r["id"]: r["top"] == r["label"] for r in real["C0 v3"]},
                                      {r["id"]: r["top"] == r["label"] for r in real["C0 v2"]})
    L.append(f"\nCorrect scenario, v3 - v2: {d:+.1f} points [{lo:+.1f}, {hi:+.1f}], McNemar p={p:.3f} (n={n}).\n")
    for name, rs in real.items():
        bad = sorted((r for r in rs if nhom[r["top"]] == "binh_thuong"), key=lambda r: r["id"])
        L += [f"Narratives {name} calls ordinary ({len(bad)}); summary from the narrative file (Vietnamese, cut at "
              "160 characters):\n", "| Narrative | Label | Answer | p(answer) | Summary |", "|---|---|---|---|---|"]
        for r in bad:
            nr = narr.get(r["id"], {})
            summ = " ".join(nr.get("tom_tat", "").split())
            summ = summ if len(summ) <= 160 else summ[:157].rstrip() + "..."
            L.append(f"| `{nr.get('id', r['id'])}` | `{r['label']}` | `{r['top']}` | {r['conf']:.2f} | {summ} |")
        L.append("")
    write("report.md", L + stories(scen, rows, 5))


if __name__ == "__main__":
    main()
