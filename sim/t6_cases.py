"""T6 part A: test set v2 in sim/cases_v2/, worded by GPT (brief docs/tasks/T6-test-set-v2.md).

475 cases: 15 per scam scenario, 25 per ordinary scenario. Tables by `sim.cases.make_case` (T4b generator) with seed
20261128; personas in rotation as in v1. The purpose line `viec` of each case is written by GPT per scenario (not the 78
train lines of sim/viec_dang_lam.yaml, which C0 v3 learned), one different line per case; the opening by GPT with
`OPENING_PROMPT`. Ordinary cases are re-read by GPT against the 15 scam catalogue lines; a flagged case is dropped and
replaced by the next index of its scenario, at most two rounds; more than 20% dropped in one scenario stops the run.
Scam cases are never filtered.

Files: `<scenario>__<i>.json` (one per kept case, same keys as sim/cases/ plus `viec` and, for ordinary cases,
`doc_lai`), `_viec.json` (the GPT lines per scenario, rejected lines), `_dropped.json`, `_cost.json`.
An evaluation set only: nobody trains on it, and the sonnet tab must not read it.

  python -m sim.t6_cases [--cap-usd 1.5] [--chunk 25] [--workers 6]

Part A2 (planner, 2026-11-26): the purpose lines of three scam scenarios drifted off their subject, because the
prompt forbade paraphrasing the train lines. `--a2` rewrites `viec` and `tin_mo_dau` of their 45 cases with
`VIEC_PROMPT_A2` (a core purpose given verbatim by the brief); tables, personas and ids stay. Old case files and the old
`_viec.json` entries go to `_replaced/`, their Part C sessions to experiments/T6/sessions_replaced.jsonl; old and new
side by side in experiments/T6/a2.md.

  python -m sim.t6_cases --a2 [--cap-usd 1.6]
"""
from __future__ import annotations

import argparse
import json
import random
import threading
import shutil
from concurrent.futures import ThreadPoolExecutor

from core import llm
from core.scenarios import ROOT, load
from sim.cases import VIEC, make_case, write_opening

CASE_DIR = ROOT / "sim/cases_v2"
VIEC_FILE, DROP_FILE, COST_FILE = CASE_DIR / "_viec.json", CASE_DIR / "_dropped.json", CASE_DIR / "_cost.json"
REPLACED = CASE_DIR / "_replaced"
T6_OUT = ROOT / "experiments/T6"
SEED = 20261128
MODEL = "openai:gpt-6.2-sol"
N_CASES = {"lua_dao": 15, "binh_thuong": 25}
SPARE = 10  # extra purpose lines per scenario, for replacements
MAX_ROUNDS = 2  # replacement rounds after the first pass
DROP_LIMIT = 0.20

VIEC_PROMPT = """Viết {n} dòng "việc đang làm" cho một kiểu tình huống chuyển tiền. Mỗi dòng là điều người dùng tin rằng \
mình đang chuyển tiền để làm, nói bằng lời của chính họ, ngắn (6-18 chữ), tiếng Việt có dấu.

Tình huống: {ten}
Mô tả: {mo_ta}
Các bước thường gặp:
{cac_buoc}

Những dòng dưới đây đã có. Không dùng lại, không viết lại chúng theo cách khác; hãy nghĩ ra những hoàn cảnh cụ thể \
khác cùng loại:
{train}

Yêu cầu:
- Đúng {n} dòng, mỗi dòng một hoàn cảnh cụ thể khác nhau (người nhận, món hàng hay dịch vụ, khoản tiền, nơi chốn khác \
nhau).
- Viết như người dùng tin đó là chuyện thật: không nêu tên tình huống, không dùng từ "lừa đảo", không nói mình nghi \
ngờ.
Trả về JSON {{"viec": [ ... ]}}."""
VIEC_SCHEMA = {"type": "object", "properties": {"viec": {"type": "array", "items": {"type": "string"}}},
               "required": ["viec"]}

# Part A2: the "do not paraphrase" paragraph is replaced by "do not copy" plus a core purpose (cores verbatim from the
# brief); everything else as VIEC_PROMPT.
VIEC_PROMPT_A2 = VIEC_PROMPT.replace(
    "Không dùng lại, không viết lại chúng theo cách khác; hãy nghĩ ra những hoàn cảnh cụ thể khác cùng loại:\n{train}",
    "Không chép nguyên văn:\n{train}\n\nMỗi dòng phải giữ đúng việc cốt lõi sau, chỉ đổi hoàn cảnh cụ thể: {core}")
assert VIEC_PROMPT_A2 != VIEC_PROMPT
A2_CORES = {
    "chuyen_nham_tien": "Người dùng đang trả lại một khoản tiền lạ vừa vào tài khoản của mình, vì có người liên lạc nói "
                        "là họ chuyển nhầm. Dòng nào cũng phải nói rõ đây là trả lại tiền người ta chuyển nhầm. Đổi số "
                        "tiền, cách người kia liên lạc, nơi được bảo trả về (một số tài khoản khác, mã QR, đường link), "
                        "hoặc việc khoản tiền bị gọi là tiền vay và bị đòi thêm lãi.",
    "gia_don_hang_lon_mua_ho": "Người dùng là người bán hàng hoặc làm dịch vụ, đang chuyển tiền cọc hoặc tiền hàng cho "
                               "một nhà cung cấp do chính vị khách đặt đơn lớn giới thiệu, để lấy hộ khách món hàng "
                               "mình không có sẵn. Dòng nào cũng phải nói rõ là mua hộ hoặc lấy hàng hộ khách đặt đơn, "
                               "và bên nhận tiền là chỗ khách giới thiệu. Đổi loại cửa hàng, món hàng, đơn vị của khách "
                               "(doanh trại, bệnh viện, trường học), khoản tiền.",
    "mo_vi_tra_sau_nhan_hoa_hong": "Người dùng đang chuyển chính số tiền vừa vay hoặc vừa được ứng (ví trả sau, vay "
                                   "nhanh trên ví, hạn mức mua trả góp) cho người hoặc 'dịch vụ' đã hướng dẫn mình, để "
                                   "nhận hoa hồng, ưu đãi, hoặc vì được hứa sẽ hủy khoản vay. Dòng nào cũng phải nói rõ "
                                   "tiền chuyển đi là tiền vừa vay hoặc vừa được ứng. Đổi nguồn tiền, người hướng dẫn, "
                                   "lời hứa, khoản tiền.",
}
# Keyword check for a2.md only (not a filter): does the line / opening carry the core?
A2_KEYS = {"chuyen_nham_tien": ("nhầm",), "gia_don_hang_lon_mua_ho": ("hộ",),
           "mo_vi_tra_sau_nhan_hoa_hong": ("vay", "ứng", "trả sau", "trả góp")}

REREAD_PROMPT = """Danh sách các kiểu lừa đảo chuyển tiền:
{catalog}

Dưới đây là câu trả lời của {n} người dùng ví điện tử khác nhau, không liên quan đến nhau, khi được hỏi "Bạn đang \
chuyển khoản này vì việc gì?":
{msgs}

Xét riêng từng câu: câu đó có kể một chuyện thuộc một kiểu lừa đảo trong danh sách không? mau_thuan = true chỉ khi câu \
đó có chi tiết mà kiểu lừa đảo đó mô tả; chỉ giống chủ đề chung (cũng là đặt cọc, cũng là trả tiền shipper, cũng là \
chuyển cho người thân) thì chưa đủ. kich_ban: mã kiểu lừa đảo khớp nhất, chuỗi rỗng nếu mau_thuan = false. ly_do: một \
câu ngắn. Trả một mục cho mỗi số thứ tự."""


def reread_schema(scam_ids):
    item = {"type": "object", "properties": {"so": {"type": "integer"}, "mau_thuan": {"type": "boolean"},
                                             "kich_ban": {"type": "string", "enum": scam_ids + [""]},
                                             "ly_do": {"type": "string"}},
            "required": ["so", "mau_thuan", "kich_ban", "ly_do"]}
    return {"type": "object", "properties": {"ket_qua": {"type": "array", "items": item}}, "required": ["ket_qua"]}


def norm(s: str) -> str:
    return " ".join(s.lower().split()).strip(" .")


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def clean_lines(lines, train) -> tuple[list[str], list[str], list[str]]:
    """(kept, equal to a train line after lower-casing and stripping, duplicates within the scenario)."""
    seen, kept, rej, dup = set(), [], [], []
    bad = {norm(t) for t in train}
    for line in (" ".join(x.split()) for x in lines):
        if not line:
            continue
        if norm(line) in bad:
            rej.append(line)
        elif norm(line) in seen:
            dup.append(line)
        else:
            seen.add(norm(line))
            kept.append(line)
    return kept, rej, dup


def write_lines(s, n, core=None) -> dict:
    fmt = dict(n=n, ten=s.ten, mo_ta=s.mo_ta, cac_buoc="\n".join(f"- {x}" for x in s.raw["cac_buoc"]),
               train="\n".join(f"- {x}" for x in VIEC[s.id]))
    p = VIEC_PROMPT_A2.format(core=core, **fmt) if core else VIEC_PROMPT.format(**fmt)
    r = llm.generate(p, schema=VIEC_SCHEMA, model=MODEL)
    kept, rej, dup = clean_lines(r.output["viec"], VIEC[s.id])
    return {"lines": kept, "rejected_train": rej, "duplicates": dup, "asked": n, "returned": len(r.output["viec"]),
            "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "usd": r.usd, **({"core": core} if core else {})}


def round_robin(items_by_sid: dict[str, list]) -> list:
    """Interleave per-scenario lists: index 0 of every scenario (sorted ids), then index 1, ..."""
    out, depth = [], max((len(v) for v in items_by_sid.values()), default=0)
    for i in range(depth):
        out += [v[i] for _, v in sorted(items_by_sid.items()) if i < len(v)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap-usd", type=float, default=1.5, help="cap on all part A spend, earlier runs included")
    ap.add_argument("--chunk", type=int, default=25,
                    help="cases per chunk (openings in parallel, then one re-read call for the chunk's ordinary "
                         "ones); the cost of the rest is projected after the first chunk, stop if over the cap")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--a2", action="store_true", help="Part A2: rewrite the three drifted scam scenarios")
    a = ap.parse_args()
    scen, issues = load()
    assert not issues, issues
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    cost = read_json(COST_FILE, {"model": MODEL, "calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0})
    base, lock = dict(cost), threading.Lock()

    def save_cost():
        u = llm.USAGE
        cost.update(calls=base["calls"] + u.calls, tokens_in=base["tokens_in"] + u.tokens_in,
                    tokens_out=base["tokens_out"] + u.tokens_out, usd=round(base["usd"] + u.usd, 5))
        write_json(COST_FILE, cost)

    def spent():
        return base["usd"] + llm.USAGE.usd

    if a.a2:
        return part_a2(scen, a, spent, save_cost)
    # ---- purpose lines, one call per scenario
    viec = read_json(VIEC_FILE, {})
    todo = [sid for sid in sorted(scen) if sid not in viec]

    def lines_for(sid):
        try:
            return write_lines(scen[sid], N_CASES[scen[sid].nhom] + SPARE)
        except Exception as e:
            print(f"  purpose lines {sid}: {type(e).__name__}: {str(e)[:160]}", flush=True)

    if todo:
        with ThreadPoolExecutor(a.workers) as ex:
            for sid, got in zip(todo, ex.map(lines_for, todo)):
                if got:
                    viec[sid] = got
        write_json(VIEC_FILE, viec)
        save_cost()
    missing = [sid for sid in scen if sid not in viec]
    assert not missing, f"no purpose lines for {missing}; rerun"
    short = {sid: len(v["lines"]) for sid, v in viec.items() if len(v["lines"]) < N_CASES[scen[sid].nhom]}
    assert not short, f"fewer purpose lines than cases: {short}"
    print(f"purpose lines: {sum(len(v['lines']) for v in viec.values())} kept, "
          f"{sum(len(v['rejected_train']) for v in viec.values())} equal to a train line, "
          f"{sum(len(v['duplicates']) for v in viec.values())} duplicates; spent {spent():.4f} USD", flush=True)

    # ---- cases: tables for every index that has a line (fixed by seed, whatever is used)
    pool = {}
    for sid in sorted(scen):
        rng = random.Random(f"{SEED}:{sid}:cases_v2")
        pool[sid] = [make_case(sid, i, scen, rng, viec=line) for i, line in enumerate(viec[sid]["lines"])]
    scam_ids = sorted(s for s in scen if scen[s].nhom == "lua_dao")
    catalog = "\n".join(f"- {s}: {scen[s].ten} - {scen[s].mo_ta}" for s in scam_ids)
    schema = reread_schema(scam_ids)
    dropped = read_json(DROP_FILE, [])
    state = {"halt": "", "n": 0, "open": [], "reread": []}

    def opening(job):
        case, rnd = job
        with lock:
            u = llm.USAGE
            if state["halt"] or spent() + a.workers * (u.usd / u.calls if u.calls else 0) >= a.cap_usd:
                state["halt"] = state["halt"] or "cap"
                return None
        try:
            c = write_opening(dict(case), scen, model=MODEL)
        except Exception as e:  # left unwritten: a rerun picks the index up again
            print(f"  {case['id']}: {type(e).__name__}: {str(e)[:160]}", flush=True)
            return None
        c["vong"] = rnd
        return c

    def reread(cases):
        """One call for a chunk's ordinary openings, numbered from 1; sets `doc_lai`. Cases left without a verdict
        (missing from the reply or a failed call) get none and are not written."""
        msgs = "\n".join(f"{i}. \"{c['tin_mo_dau']}\"" for i, c in enumerate(cases, 1))
        try:
            r = llm.generate(REREAD_PROMPT.format(catalog=catalog, n=len(cases), msgs=msgs), schema=schema,
                             model=MODEL)
        except Exception as e:
            print(f"  re-read of {len(cases)}: {type(e).__name__}: {str(e)[:160]}", flush=True)
            return
        got = {it["so"]: it for it in r.output["ket_qua"] if isinstance(it.get("so"), int)}
        for i, c in enumerate(cases, 1):
            if i in got:
                c["doc_lai"] = {**{k: got[i][k] for k in ("mau_thuan", "kich_ban", "ly_do")}, "model": r.model,
                                "batch": len(cases), "usd_share": r.usd / len(cases)}
        state["reread"].append(r.usd / len(cases))

    def run_chunk(chunk):
        with ThreadPoolExecutor(a.workers) as ex:
            got = [c for c in ex.map(opening, chunk) if c]
        ords = [c for c in got if c["nhom"] == "binh_thuong"]
        if ords:
            reread(ords)
        with lock:
            for c in got:
                state["n"] += 1
                state["open"].append(c["sinh_boi"]["usd"])
                if c["nhom"] == "binh_thuong" and "doc_lai" not in c:
                    print(f"  {c['id']}: no re-read verdict, not written", flush=True)
                elif c.get("doc_lai", {}).get("mau_thuan"):
                    dropped.append(c)
                else:
                    write_json(CASE_DIR / f"{c['id']}.json", c)
            write_json(DROP_FILE, dropped)
            save_cost()

    def kept(sid):
        return sorted(CASE_DIR.glob(f"{sid}__*.json"))

    for rnd in range(MAX_ROUNDS + 1):
        used = {sid: {json.loads(p.read_text(encoding="utf-8"))["id"] for p in kept(sid)}
                | {d["id"] for d in dropped if d["kich_ban"] == sid} for sid in scen}
        jobs = {}
        for sid in sorted(scen):
            need = N_CASES[scen[sid].nhom] - len(kept(sid))
            if rnd == 0:  # first pass: indexes below the target only
                free = [c for c in pool[sid][:N_CASES[scen[sid].nhom]] if c["id"] not in used[sid]]
            else:  # replacements for drops of the previous round
                free = [c for c in pool[sid] if c["id"] not in used[sid]
                        and int(c["id"].rsplit("__", 1)[1]) >= N_CASES[scen[sid].nhom]]
            jobs[sid] = [(c, rnd) for c in free[:max(need, 0)]]
        order = round_robin(jobs)
        if not order:
            continue
        print(f"round {rnd}: {len(order)} cases to write; spent {spent():.4f} USD", flush=True)
        for k in range(0, len(order), a.chunk):
            if state["halt"]:
                break
            run_chunk(order[k:k + a.chunk])
            print(f"  {min(k + a.chunk, len(order))}/{len(order)} cases, {spent():.4f} USD", flush=True)
            rest = order[k + a.chunk:]
            if rnd == 0 and k == 0 and rest and not state["halt"]:
                if not state["open"]:
                    state["halt"] = "no case written before the projection"
                    break
                m_open = sum(state["open"]) / len(state["open"])
                m_re = sum(state["reread"]) / len(state["reread"]) if state["reread"] else 0.0
                n_ord = sum(c["nhom"] == "binh_thuong" for c, _ in rest)
                proj = spent() + m_open * len(rest) + m_re * n_ord
                print(f"PROJECTION after {state['n']} cases: {proj:.3f} USD for part A without replacements "
                      f"(opening {m_open:.5f}, re-read {m_re:.5f} USD per case; cap {a.cap_usd})", flush=True)
                if proj > a.cap_usd:
                    state["halt"] = "projection"
        if state["halt"]:
            print(f"STOPPED ({state['halt']}) at {spent():.4f} USD", flush=True)
            break
        over = {sid: k for sid in scen if (k := sum(d["kich_ban"] == sid for d in dropped))
                > DROP_LIMIT * N_CASES[scen[sid].nhom]}
        if over:
            state["halt"] = "drop rule"
            print(f"STOPPED by the 20% rule: {over}", flush=True)
            break
    n = {sid: len(kept(sid)) for sid in scen}
    print(f"{sum(n.values())} cases kept in {CASE_DIR.relative_to(ROOT)}, {len(dropped)} dropped; part A spend "
          f"{spent():.4f} USD; short: {({s: k for s, k in n.items() if k < N_CASES[scen[s].nhom]})}")


def has_core(sid, text):
    return any(k in text.lower() for k in A2_KEYS[sid])


def part_a2(scen, a, spent, save_cost):
    """Rewrite `viec` and `tin_mo_dau` of the cases of A2_CORES; tables, personas, ids and `vong` stay. Resumable: a
    case whose old file is already in _replaced/ is done."""
    REPLACED.mkdir(exist_ok=True)
    viec, old_viec = read_json(VIEC_FILE, {}), read_json(REPLACED / "_viec.json", {})
    for sid in A2_CORES:
        if sid in old_viec:  # lines already rewritten
            continue
        if spent() >= a.cap_usd:
            print(f"STOPPED (cap) at {spent():.4f} USD before the lines of {sid}", flush=True)
            return
        got = write_lines(scen[sid], N_CASES[scen[sid].nhom] + SPARE, core=A2_CORES[sid])
        assert len(got["lines"]) >= N_CASES[scen[sid].nhom], (sid, len(got["lines"]))
        old_viec[sid], viec[sid] = viec[sid], {**got, "a2": True}
        write_json(REPLACED / "_viec.json", old_viec)
        write_json(VIEC_FILE, viec)
        save_cost()
        print(f"A2 purpose lines {sid}: {len(got['lines'])} kept, {len(got['rejected_train'])} equal to a train "
              f"line, {sum(has_core(sid, x) for x in got['lines'])} with the core keyword; {spent():.4f} USD", flush=True)
    # Part C sessions of the old cases: moved once, before any new session can exist for these ids
    sess, moved = T6_OUT / "sessions.jsonl", T6_OUT / "sessions_replaced.jsonl"
    if sess.exists() and not moved.exists():
        rows = [json.loads(l) for l in open(sess, encoding="utf-8")]
        old = [r for r in rows if r.get("kich_ban") in A2_CORES]
        moved.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old), encoding="utf-8")
        sess.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows if r not in old),
                        encoding="utf-8")
        print(f"A2: {len(old)} Part C sessions moved to {moved.relative_to(ROOT)}", flush=True)
    todo = [p for sid in sorted(A2_CORES) for p in sorted(CASE_DIR.glob(f"{sid}__*.json"))
            if not (REPLACED / p.name).exists()]
    lock = threading.Lock()

    def redo(p):
        old = json.loads(p.read_text(encoding="utf-8"))
        with lock:
            if spent() >= a.cap_usd:
                return f"{old['id']}: cap"
        i = int(old["id"].rsplit("__", 1)[1])
        case = {k: v for k, v in old.items() if k not in ("tin_mo_dau", "sinh_boi")}
        case["viec"] = viec[old["kich_ban"]]["lines"][i]
        try:
            new = write_opening(case, scen, model=MODEL)
        except Exception as e:
            return f"{old['id']}: {type(e).__name__}: {str(e)[:160]}"
        new["a2"] = True
        with lock:
            shutil.move(p, REPLACED / p.name)
            write_json(p, new)
            save_cost()

    with ThreadPoolExecutor(a.workers) as ex:
        for err in ex.map(redo, todo):
            if err:
                print("  " + err, flush=True)
    left = [p.name for p in todo if not (REPLACED / p.name).exists()]
    write_a2_md(scen, viec, old_viec, spent())
    print(f"A2: {len(todo) - len(left)} of {len(todo)} cases rewritten; left {left}; part A spend {spent():.4f} USD",
          flush=True)


def write_a2_md(scen, viec, old_viec, usd):
    L = ["# T6 part A2 - three scam scenarios rewritten, old and new side by side\n",
         f"`python -m sim.t6_cases --a2`. Same tables, personas and ids; new `viec` (`VIEC_PROMPT_A2`: \"không chép "
         f"nguyên văn\" plus the core purpose of the brief, verbatim) and new opening (`OPENING_PROMPT`, `{MODEL}`). "
         f"Part A spend so far, A2 included: {usd:.4f} USD (cap 1.6). Keyword check (not a filter): "
         + "; ".join(f"`{s}` {' / '.join(repr(k) for k in A2_KEYS[s])}" for s in A2_CORES) + ".\n",
         "| Scenario | Old lines with the keyword | New lines (all, spares included) | Old openings | New openings |",
         "|---|---|---|---|---|"]
    cases = {sid: [(json.loads(p.read_text(encoding="utf-8")),
                    json.loads((REPLACED / p.name).read_text(encoding="utf-8")) if (REPLACED / p.name).exists() else None)
                   for p in sorted(CASE_DIR.glob(f"{sid}__*.json"), key=lambda p: int(p.stem.rsplit("__", 1)[1]))]
             for sid in A2_CORES}
    for sid in A2_CORES:
        pairs = [(n, o) for n, o in cases[sid] if o]
        ol, nl = old_viec.get(sid, {}).get("lines", []), viec[sid]["lines"]
        L.append(f"| `{sid}` | {sum(has_core(sid, x) for x in ol)}/{len(ol)} | {sum(has_core(sid, x) for x in nl)}/"
                 f"{len(nl)} | {sum(has_core(sid, o['tin_mo_dau']) for _, o in pairs)}/{len(pairs)} | "
                 f"{sum(has_core(sid, n['tin_mo_dau']) for n, _ in pairs)}/{len(pairs)} |")
    for sid in A2_CORES:
        L += [f"\n## `{sid}`: {scen[sid].ten}\n", f"Core: *{A2_CORES[sid]}*\n",
              "Spare lines (not used by a case): " + "; ".join(viec[sid]["lines"][N_CASES['lua_dao']:]) + "\n"]
        for new, old in cases[sid]:
            if not old:
                L.append(f"### `{new['id']}`: not rewritten yet\n")
                continue
            t = new["tai_khoan"]
            L += [f"### `{new['id']}` (persona `{new['tinh_cach']}`; account `{t['nhan_tai_khoan']}`, "
                  f"`{t['loai_tai_khoan']}`, name matches: `{t['ten_khop_tu_xung']}`)\n",
                  "| | Old | New |", "|---|---|---|",
                  f"| Purpose line | {old['viec']} | {new['viec']} |",
                  f"| Opening | {old['tin_mo_dau']} | {new['tin_mo_dau']} |", ""]
    T6_OUT.mkdir(parents=True, exist_ok=True)
    (T6_OUT / "a2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"A2: wrote {(T6_OUT / 'a2.md').relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
