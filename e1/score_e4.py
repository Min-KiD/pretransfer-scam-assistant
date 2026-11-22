"""E4 phase A report: every reader (regex on OCR, closed and open VLMs, OCR text -> LLM) on the four image sets.

  python -m e1.score_e4 [--out experiments/E4]   -> report_A.md, summary_A.json, terminal summary

Per config and split: string match (Wilson 95%), per type, made-up strings ("chuỗi bịa": returned strings that are
not in the answer, over strings returned; strings in an answer's `skipped`/`ignore` excluded), valid JSON, sender side,
s/image, VRAM, USD per 1000 images. `web` is split by id: odd = web-dev (errors may be read), even = web-test (only
numbers). M1 (plan section 5) is checked on web-test against gemini-3.5-flash-lite.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from core.llm import PRICES
from e1.score import TYPES, TYPE_VI, wilson
from e1.score_e1b import agg, build, cell, fabricated, link_split, speed

ROOT = Path(__file__).resolve().parent.parent
BASE = "J__gemini-3.5-flash-lite"
SPLITS = ["E1", "E1b", "gen", "gen_ref", "val", "val_la", "web-dev", "web-test", "web"]
MODE_VI = {"A": "OCR CPU + regex", "T": "OCR/chữ + regex", "J": "ảnh -> JSON (ràng buộc)",
           "Ju": "ảnh -> JSON (không ràng buộc)", "O": "chữ OCR -> LLM -> JSON",
           "JO": "ảnh + chữ OCR -> JSON (ràng buộc)"}
OCR_RUN = "T__pp-ocrv6-gpu"
LORA = re.compile(r"^J?O?__B\d")  # phase-B adapters, served as local:<run>-<step>


def b4_check(results, sets, config: str):
    """B4: an account or phone number the model returns must appear in the PP-OCRv6 text (spaces and dots removed,
    lines joined so wrapped strings still count; +84 read as 0). Per split: (wrong strings flagged, wrong strings),
    (right strings flagged, right strings). Strings matching `skipped`/`ignore` are left out as in fabricated()."""
    from e1.score import NORMALIZERS
    from e1.vlm import RUN_DIRS

    def sq(s):
        return re.sub(r"[\s.]", "", s).replace("+84", "0")

    out = {}
    for r in results:
        if r["config"] != config or r.get("missing"):
            continue
        op = ROOT / RUN_DIRS[r["set"]] / OCR_RUN / f"{r['image_id']}.json"
        if not op.exists():
            continue
        blob = sq("".join(x["text"] for x in json.loads(op.read_text(encoding="utf-8")).get("lines", [])))
        gt = sets[r["set"]][r["image_id"]]
        ignore = {(s["type"], s["norm"]) for s in gt["ignore"]["strings"]}
        skipped = {(s["type"], NORMALIZERS[s["type"]](s.get("seen", ""))) for s in gt.get("skipped") or []
                   if s.get("type") in NORMALIZERS}
        for split in [r["set"]] + ([web_split(r["image_id"])] if r["set"] == "web" else []):
            c = out.setdefault(split, [0, 0, 0, 0])
            for t in ("account", "phone"):
                gts = {e["norm"] for e in gt["strings"][t]}
                for p in r["pred"].get(t, []):
                    pn = NORMALIZERS[t](p)
                    if (t, pn) in ignore or (t, pn) in skipped:
                        continue
                    flag = sq(p) not in blob
                    if pn in gts:
                        c[2] += flag
                        c[3] += 1
                    else:
                        c[0] += flag
                        c[1] += 1
    return out


def web_split(image_id: str) -> str:
    m = re.search(r"(\d+)$", image_id)
    return "web-dev" if int(m.group(1)) % 2 else "web-test"


def split_rows(results):
    out = {}
    for r in results:
        keys = [r["set"]] + ([web_split(r["image_id"])] if r["set"] == "web" else [])
        for k in keys:
            out.setdefault((k, r["config"]), []).append(r)
    return out


def usd_per_image(r) -> float | None:
    if "usd" in r:
        return r["usd"]
    if "tokens_in" not in r:
        return None
    name = r["model"].split(":", 1)[-1].split("@")[0]
    pin, pout = PRICES.get(name, (0.0, 0.0))
    return (r["tokens_in"] * pin + (r.get("tokens_out", 0) + r.get("tokens_thought", 0)) * pout) / 1e6


def metrics(rows, sets):
    live = [r for r in rows if not r.get("missing")]
    k, n = agg(live)
    fab = ret = 0
    fab_t = {t: [0, 0] for t in TYPES}
    for r in live:
        f, nn = fabricated(r, sets[r["set"]][r["image_id"]])
        for t in TYPES:
            fab_t[t][0] += f[t]
            fab_t[t][1] += nn[t]
        fab += sum(f.values())
        ret += sum(nn.values())
    js = [r for r in live if r["group"] == "J"]
    sp = speed(live)
    usd = [u for u in (usd_per_image(r) for r in live) if u is not None]
    paid = any(u > 0 for u in usd)  # self-hosted models have no price, so their USD is 0
    return {
        "images": len(live), "total": len(rows), "match": (k, n),
        "types": {t: agg(live, t=t) for t in TYPES}, "fab": (fab, ret), "fab_types": fab_t,
        "json_ok": (sum(not r.get("json_broken") for r in js), len(js)) if js else None,
        "side": (sum(r.get("side_correct", 0) for r in js), sum(r.get("side_total", 0) for r in js)) if js else None,
        "cer": (sum(r.get("msg_char_err", 0) for r in js), sum(r.get("msg_chars", 0) for r in js)) if js else None,
        "link_dp": link_split(live),
        "speed": sp, "workers": max((r.get("workers", 1) for r in live), default=1),
        "usd_1000": 1000 * sum(usd) / len(usd) if paid else None,
    }


def pp(x):
    k, n = x
    return k / n if n else float("nan")


def fmt(x, ci=True):
    return cell(*x, ci=ci) if x and x[1] else "-"


def gt_audit(results, sets, M) -> list[str]:
    """Answers of the web set checked against the two strongest closed models (by web string match): a GT string that
    both models read differently, or a string both models return that the answer lacks (and is not in skipped/ignore).
    Nothing is changed; the planner tab looks at the image and fixes the answer."""
    from e1.score import NORMALIZERS
    closed = [c for (s, c), m in M.items() if s == "web" and c.startswith("J__") and m["images"] == m["total"]
              and any(k in c for k in ("gemini", "gpt", "claude"))]
    top = sorted(closed, key=lambda c: -pp(M[("web", c)]["match"]))[:2]
    L = ["# E4 - Soát đáp án bộ `web`\n",
         f"So đáp án với hai model đóng đọc tốt nhất trên `web`: {', '.join(f'`{c}`' for c in top)}. Ghi một dòng khi "
         "cả hai cùng đọc khác đáp án (cả hai không có chuỗi đáp án), hoặc cả hai cùng trả một chuỗi mà đáp án không có "
         "(không tính chuỗi trong `skipped`/`ignore`). Không tự sửa đáp án; tab kế hoạch xem ảnh rồi sửa.\n"]
    if len(top) < 2:
        return L + ["Chưa đủ hai model đóng chạy hết bộ `web`.\n"]
    rows = {(r["config"], r["image_id"]): r for r in results if r["set"] == "web" and r["config"] in top}
    L += ["| Ảnh | Loại | Vấn đề | Đáp án | " + " | ".join(f"`{c[3:]}`" for c in top) + " |", "|---|---|---|---|---|---|"]
    n = 0
    esc = lambda s: "`" + str(s).replace("\n", "⏎").replace("|", "\\|") + "`"  # noqa: E731
    for iid, gt in sorted(sets.get("web", {}).items()):
        a, b = rows.get((top[0], iid)), rows.get((top[1], iid))
        if not a or not b or a.get("missing") or b.get("missing"):
            continue
        for t in TYPES:
            for ga, gb in zip(a["scores"][t]["gt"], b["scores"][t]["gt"]):
                if not ga["correct"] and not gb["correct"]:
                    n += 1
                    L.append(f"| {iid} | {t} | cả hai đọc khác | {esc(ga['gt'])} | "
                             f"{esc(ga.get('closest', '(không có)'))} | {esc(gb.get('closest', '(không có)'))} |")
            fb = {NORMALIZERS[t](p): p for p in b["scores"][t]["fp"]}
            skipped = {NORMALIZERS[t](s.get("seen", "")) for s in gt.get("skipped") or [] if s.get("type") == t}
            for p in a["scores"][t]["fp"]:
                pn = NORMALIZERS[t](p)
                if pn in fb and pn not in skipped:
                    n += 1
                    L.append(f"| {iid} | {t} | cả hai trả chuỗi đáp án không có | - | {esc(p)} | {esc(fb[pn])} |")
    L.append(f"\n{n} dòng cần xem trên {len(sets.get('web', {}))} ảnh có đáp án.\n")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="experiments/E4")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    results, sets = build(ROOT, b_models=None)
    by = split_rows(results)
    meta = json.loads((out / "open_meta.json").read_text()) if (out / "open_meta.json").exists() else {}
    M = {key: metrics(rows, sets) for key, rows in by.items()}
    configs = sorted({c for _, c in M}, key=lambda c: (c.split("__")[0] != "J" or "gemini" not in c, c))
    L = ["# E4 giai đoạn A - Đọc ảnh chat ra JSON: baseline trên các bộ có sẵn\n",
         "Không train gì ở giai đoạn này. Mỗi cấu hình chạy đúng một lần (không chạy lại để chọn kết quả tốt). Tỉ lệ ghi "
         "`tử/mẫu` và khoảng tin cậy Wilson 95%. `web` chia theo số thứ tự ảnh: lẻ là `web-dev` (được mở lỗi ra xem), "
         "chẵn là `web-test` (chỉ xem số). Chuỗi bịa = chuỗi model trả về mà không có trong đáp án, chia cho số chuỗi "
         "model trả về; chuỗi đáp án ghi ở `skipped` (bị che, mờ, bị cắt) hoặc `ignore` không tính.\n",
         "Cấu hình: " + "; ".join(f"`{k}` = {v}" for k, v in MODE_VI.items()) + ". `J__gemini-*` không có hậu tố "
         "`@low` là lần chạy của E1 (thinking mặc định).\n"]
    for s in SPLITS:
        cs = [c for c in configs if (s, c) in M]
        if not cs:
            continue
        n_img = max(M[(s, c)]["total"] for c in cs)
        L.append(f"## {s} ({n_img} ảnh)\n")
        partial = [c for c in cs if M[(s, c)]["images"] < n_img]
        if partial:
            L.append("Chưa chạy đủ ảnh (không so trực tiếp với các dòng đủ ảnh): "
                     + ", ".join(f"`{c}` {M[(s, c)]['images']}/{n_img}" for c in partial) + ".\n")
        if s == "gen_ref":
            rs = ROOT / "data/E1b/gen_ref/review_summary.json"
            if rs.exists():
                r = json.loads(rs.read_text(encoding="utf-8"))
                L.append(f"{r['images']} ảnh sinh bằng `gemini-nano-banana-2.1`, mỗi ảnh lấy một ảnh thật làm mẫu giao diện "
                         f"và kiểu chụp, nội dung mới (`e1/gen_nb.py --ref`). Đáp án: {r['strings']} chuỗi dự định; "
                         f"{r['kept'] + r.get('kept_fold', 0)} giữ vì `gemini-4-carbon` và chữ PP-OCRv6 cùng đọc lại "
                         f"({r.get('kept_fold', 0)} trong đó chỉ khác I/l hoặc O/0 ở OCR); {r['auto_fixed']} sửa theo "
                         f"chuỗi hai bên cùng đọc; {r['reviewed_kept'] + r['reviewed_fixed'] + r['reviewed_dropped']} "
                         f"xem bằng mắt ({r['reviewed_fixed']} sửa, {r['reviewed_dropped']} bỏ); "
                         f"{r['dropped_images']} ảnh bị loại; {r['copy_flags']} ảnh chép chuỗi của ảnh mẫu. "
                         "**`gemini-4-carbon` đã được dùng để làm đáp án bộ này, nên số của nó ở đây lệch về phía có lợi; "
                         "không dùng để so.**\n")
        L.append("| Cấu hình | Ảnh | Khớp chuỗi | Chuỗi bịa | JSON hợp lệ | Phía gửi | Lỗi ký tự chữ tin | s/ảnh TB | p50 | "
                 "p90 | USD/1000 ảnh |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for c in cs:
            m = M[(s, c)]
            sp = m["speed"]
            L.append(f"| `{c}` | {m['images']}/{m['total']} | {fmt(m['match'])} | {fmt(m['fab'])} | "
                     f"{fmt(m['json_ok'], False)} | {fmt(m['side'], False)} | {fmt(m['cer'], False)} | "
                     + (f"{sp[0]:.2f} | {sp[1]:.2f} | {sp[2]:.2f}" if sp else "- | - | -")
                     + f"{' (song song ' + str(m['workers']) + ')' if m['workers'] > 1 else ''} | "
                     + (f"{m['usd_1000']:.2f}" if m["usd_1000"] is not None else "0 (tự host)") + " |")
        L.append("")
        L.append(f"Theo loại chuỗi ({s}): khớp / bịa\n")
        L.append("| Cấu hình | " + " | ".join(TYPE_VI.get(t, t) for t in TYPES) + " | Link: tên miền | Link: đường dẫn |")
        L.append("|---|" + "---|" * (len(TYPES) + 2))
        for c in cs:
            m = M[(s, c)]
            dk, pk, ln = m["link_dp"]
            L.append(f"| `{c}` | " + " | ".join(
                f"{fmt(m['types'][t], False)} / bịa {m['fab_types'][t][0]}/{m['fab_types'][t][1]}" for t in TYPES)
                + f" | {fmt((dk, ln), False)} | {fmt((pk, ln), False)} |")
        L.append("")
    L.append("## Model không chạy\n")
    L.append("- `gemma-4-e4b` (16,0 GB) và `qwen3.5-9b` (19,3 GB): bỏ ngày 22/11 theo quyết định của Minh vì đĩa server "
             "dùng chung chỉ còn khoảng 24 GB trống (98%). Lý do là dung lượng, không phải kết quả; hai model này chưa "
             "chạy ảnh nào.")
    L.append("- `qwen3-vl-8b-fp8` (10,6 GB): cũng bỏ ngày 22/11 theo quyết định của Minh. Mốc \"model lớn\" trong báo "
             "cáo là các model đóng qua API (Gemini, GPT), nên không cần thêm model mở lớn. Model này cũng chưa chạy "
             "ảnh nào.\n")
    # VRAM and load time of the open models
    if meta:
        L.append("## Model mở: VRAM, nạp model\n")
        L.append("| Model | " + " | ".join(sorted({k for v in meta.values() for k in v})) + " |")
        keys = sorted({k for v in meta.values() for k in v})
        L.append("|---|" + "---|" * len(keys))
        for mname, v in meta.items():
            L.append(f"| `{mname}` | " + " | ".join(str(v.get(k, "-")) for k in keys) + " |")
        L.append("")
    # M1 on web-test
    verdicts = {}
    if ("web-test", BASE) in M:
        b = M[("web-test", BASE)]
        L.append("## Luật giữ M1 trên web-test (so với `gemini-3.5-flash-lite`)\n")
        L.append(f"Mốc: khớp {fmt(b['match'])}, bịa {fmt(b['fab'])}. Đạt khi khớp kém không quá 5 điểm, bịa cao hơn "
                 "không quá 2 điểm, p50 không quá 2 s/ảnh trên 4060 Ti (chạy 1 luồng). web-test nhỏ nên khoảng tin cậy "
                 "rộng; kết luận \"đạt\" ở đây là điều kiện cần, chưa đủ.\n")
        L.append("| Cấu hình | Khớp (chênh, điểm) | Bịa (chênh, điểm) | p50 (s) | M1 |")
        L.append("|---|---|---|---|---|")
        for c in configs:
            mm = M.get(("web-test", c))
            if not mm or not (c.startswith(("Ju__", "O__")) or f"local:{c.split('__', 1)[1]}" in meta or LORA.match(c)):
                continue
            dm = 100 * (pp(mm["match"]) - pp(b["match"]))
            df = 100 * (pp(mm["fab"]) - pp(b["fab"])) if mm["fab"][1] and b["fab"][1] else float("nan")
            p50 = mm["speed"][1] if mm["speed"] else float("nan")
            ok = dm >= -5 and (df <= 2 or mm["fab"][0] == 0) and p50 <= 2 and mm["workers"] == 1
            verdicts[c] = ok
            L.append(f"| `{c}` | {fmt(mm['match'], False)} ({dm:+.1f}) | {fmt(mm['fab'], False)} ({df:+.1f}) | "
                     f"{p50:.2f} | {'đạt' if ok else 'không đạt'} |")
        L.append("")
    # B4: OCR cross-check of the picked B1 adapter (.cache/e4/lora/B1/pick.json, copied from the server)
    pick = ROOT / ".cache/e4/lora/B1/pick.json"
    if pick.exists():
        cfg = json.loads(pick.read_text())["config"]
        b4 = b4_check(results, sets, cfg)
        if b4:
            L.append(f"## B4: soát số tài khoản, số điện thoại của `{cfg}` bằng chữ PP-OCRv6\n")
            L.append("Chuỗi model trả về không có trong chữ OCR (bỏ dấu cách, dấu chấm) thì gắn cờ.\n")
            L.append("| Bộ | Cờ bắt chuỗi sai | Cờ gắn nhầm chuỗi đúng |")
            L.append("|---|---|---|")
            for s in SPLITS:
                if s in b4:
                    w, nw, rr, nr = b4[s]
                    L.append(f"| {s} | {fmt((w, nw))} | {fmt((rr, nr))} |")
            L.append("")
    (out / "report_A.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / "gt_audit.md").write_text("\n".join(gt_audit(results, sets, M)) + "\n", encoding="utf-8")
    summ = {f"{s}|{c}": {"match": m["match"], "fab": m["fab"], "json_ok": m["json_ok"],
                         "p50": m["speed"][1] if m["speed"] else None, "usd_1000": m["usd_1000"]}
            for (s, c), m in M.items()}
    (out / "summary_A.json").write_text(json.dumps({"metrics": summ, "M1": verdicts}, ensure_ascii=False, indent=1))
    # terminal summary: web-test and gen, the two sets every model ran on
    for s in ("gen", "gen_ref", "val", "val_la", "web-dev", "web-test"):
        print(f"\n== {s}")
        for c in configs:
            m = M.get((s, c))
            if m:
                lo, hi = wilson(*m["match"]) if m["match"][1] else (0, 0)
                print(f"  {c:38s} khop {pp(m['match']) * 100:5.1f}% ({m['match'][0]}/{m['match'][1]}) "
                      f"[{lo * 100:.0f}-{hi * 100:.0f}]  bia {m['fab'][0]}/{m['fab'][1]}  "
                      f"p50 {m['speed'][1] if m['speed'] else float('nan'):.2f}s")
    print("M1:", verdicts)
    print("report:", out / "report_A.md")


if __name__ == "__main__":
    main()
