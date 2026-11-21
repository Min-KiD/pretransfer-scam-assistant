"""How much `dien_bang` fills from one message (T2).

    python -m sim.fill_eval --dev        # tests/fill_dev.json: recall of stated fields, over-filling; for prompt tuning
    python -m sim.fill_eval --openings   # opening message of every sim/cases/ case: fields filled, T1 prompt vs now

The T1 prompt is kept here verbatim (commit 3599047) only to measure "before"; the app uses core.dialog.
--openings is a measurement, not a tuning set: the prompt was tuned on the dev set only.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from core import dialog, llm
from core.scenarios import ROOT
from core.schema import ASKABLE, FIELDS
from sim.cases import CASE_DIR

T1_FILL_PROMPT = """Điền bảng câu chuyện từ câu trả lời của người dùng. Bảng có các trường sau (tên: ý nghĩa; giá trị được phép):
{fields}

Quy tắc:
- Điền MỌI trường có căn cứ rõ trong câu trả lời, kể cả trường không được hỏi (một câu thường nói được nhiều trường: kênh, \
ai nhắn trước, người kia tự xưng là ai, có hối thúc không...). Không suy đoán; không biết, né, hay mơ hồ thì không điền.
- Mỗi trường kèm "trich": câu chữ nguyên văn của người dùng làm căn cứ.
- Chỉ dùng giá trị trong danh sách; ý không khớp giá trị nào nhưng rõ ràng thì dùng "khac".
- ap_luc, yeu_cau được chọn nhiều giá trị; các trường khác đúng một giá trị.
{focus}
{data_rule}
<lich_su>
{history}
</lich_su>
<du_lieu_nguoi_dung>
{message}
</du_lieu_nguoi_dung>"""


def fill_t1(msg: str):
    """T1 behaviour: no quote check. Returns (fills, result, fills whose quote is not in the message)."""
    fields = "\n".join(f"- {n}: {FIELDS[n].label}; [{', '.join(FIELDS[n].values)}]" for n in ASKABLE)
    r = llm.generate(T1_FILL_PROMPT.format(fields=fields, focus="", data_rule=dialog.DATA_RULE, history="(chưa có)",
                                           message=msg), schema=dialog.fill_schema())
    fills = dialog.clean_fills((r.output or {}).get("dien", []))
    return fills, r, sum(not dialog.quote_in(f["trich"], msg) for f in fills)


def fill_now(msg: str):
    return dialog.dien_bang(msg, None, [])


def ok(item, f) -> bool:
    name, v = f["truong"], f["gia_tri"]
    multi = FIELDS[name].multi
    same = (lambda a, b: set(a) == set(b)) if multi else (lambda a, b: a == b)
    good = ([item["can"][name]] if name in item["can"] else []) + item["duoc"].get(name, [])
    return any(same(v, g) for g in good)


def dev():
    items = json.loads((ROOT / "tests/fill_dev.json").read_text(encoding="utf-8"))["items"]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda it: fill_now(it["tin"]), items))
    need = hit = over = dropped = 0
    for it, (fills, _, d) in zip(items, res):
        got = {f["truong"]: f for f in fills}
        miss = [n for n in it["can"] if not (n in got and ok(it, got[n]))]
        bad = [f"{f['truong']}={f['gia_tri']} ({f['trich']!r})" for f in fills if not ok(it, f)]
        need += len(it["can"])
        hit += len(it["can"]) - len(miss)
        over += len(bad)
        dropped += d
        print(f"{it['id']}: filled {len(fills)}, missed {miss or '-'}, over {bad or '-'}, dropped {d}")
    print(f"recall {hit}/{need}, over-filled {over}, dropped by quote check {dropped}, USD {llm.USAGE.usd:.4f}")


def openings():
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASE_DIR.glob("*.json"))]
    out = {}
    for name, fn in (("t1", fill_t1), ("t2", fill_now)):
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(lambda c: fn(c["tin_mo_dau"]), cases))
        n = [len(f) for f, _, _ in res]
        out[name] = {"n_cases": len(cases), "mean_fields": sum(n) / len(n),
                     "quote_not_in_message": sum(d for _, _, d in res),
                     "per_field": {k: sum(any(f["truong"] == k for f in r[0]) for r in res) for k in ASKABLE}}
        print(name, f"mean fields {out[name]['mean_fields']:.2f}", "quote not in message",
              out[name]["quote_not_in_message"], out[name]["per_field"])
    out["note"] = ("t1: T1 prompt, no quote check (quote_not_in_message = fills it would have dropped); "
                   "t2: current dien_bang (quote_not_in_message = fills dropped). One call per opening message.")
    (ROOT / "experiments/E2/fill_openings.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                                            encoding="utf-8")
    print(f"USD {llm.USAGE.usd:.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dev", action="store_true")
    g.add_argument("--openings", action="store_true")
    a = ap.parse_args()
    dev() if a.dev else openings()
