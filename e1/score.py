"""Score E1 runs and write experiments/E1/results.jsonl + report.md.

Usage: python -m e1.score --data data/E1 --out experiments/E1
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

from e1.extract import extract
from e1.scenarios import NORMALIZERS, amount_value

TYPES = ("account", "phone", "link", "amount")
TYPE_VI = {"account": "Số TK", "phone": "SĐT", "link": "Link", "amount": "Số tiền"}
VARIANTS = ("orig", "dark", "crop", "jpeg40", "half", "blur")
VARIANT_VI = {"orig": "gốc", "dark": "tối", "crop": "cắt mép trên", "jpeg40": "JPEG q40", "half": "thu nhỏ 50%",
              "blur": "mờ nhẹ"}
# USD per 1M tokens (input, output incl. thinking), read 2026-11-20 from aistudio.google.com/docs/latest-model
# and ai.google.dev/gemini-api/docs/pricing. Intro prices: 3.8-flash until 2026-12-31 (then 1.50/7.50),
# 4-carbon until 2026-11-30 (then 4.00/20.00 from 2026-12-01).
PRICES = {"gemini-3.5-flash-lite": (0.30, 2.50), "gemini-3.8-flash": (0.75, 3.75), "gemini-4-carbon": (2.00, 10.00)}
VLM_KEYS = {"account": "accounts", "phone": "phones", "link": "links", "amount": "amounts"}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def fold_il(s):
    """Collapse capital I and lowercase l, which render near-identically in sans-serif UI fonts."""
    return s.replace("I", "l")


def norm_text(s):
    return " ".join(s.lower().split())


def vlm_strings(out: dict) -> dict:
    res = {}
    for t in TYPES:
        vals = out.get(VLM_KEYS[t]) or []
        res[t] = [v["number"] if t == "account" else v for v in vals if (v.get("number") if t == "account" else v)]
    return res


def side_score(gt_msgs, pred_msgs):
    """Greedy text alignment GT->pred; a GT message counts as correct if aligned and same side."""
    pairs = []
    for i, g in enumerate(gt_msgs):
        for j, p in enumerate(pred_msgs):
            pairs.append((ratio(norm_text(g["text"]), norm_text(p.get("text", ""))), i, j))
    pairs.sort(reverse=True)
    used_g, used_p, correct = set(), set(), 0
    for r, i, j in pairs:
        if r < 0.5 or i in used_g or j in used_p:
            continue
        used_g.add(i)
        used_p.add(j)
        correct += gt_msgs[i]["side"] == pred_msgs[j].get("side")
    return correct, len(gt_msgs)


def score_strings(gt, preds: dict, flags: dict | None, a_norms: dict | None):
    """Per type: list of per-GT-string records + false positives."""
    out = {}
    ignore = {(s["type"], s["norm"]) for s in gt["ignore"]["strings"]}
    for t in TYPES:
        gts = [e["norm"] for e in gt["strings"][t]]
        pn = [NORMALIZERS[t](p) for p in preds.get(t, [])]
        pset = set(pn)
        recs = []
        for e in gt["strings"][t]:
            g = e["norm"]
            ok = g in pset
            rec = {"gt": e["raw"], "gt_norm": g, "correct": ok,
                   "il_ok": fold_il(g) in {fold_il(n) for n in pn}}
            if t == "link":  # norm_link already lower-cases the host and keeps the path as written
                gd, gp = g.partition("/")[::2]
                rec["domain_ok"] = gd in {n.partition("/")[0] for n in pn}
                rec["path_ok"] = gp in {n.partition("/")[2] for n in pn}
            if t == "amount":
                gv = amount_value(e["raw"])
                rec["value_ok"] = gv is not None and any(amount_value(p) == gv for p in preds.get(t, []))
            if flags is not None:
                if ok:
                    rec["flagged"] = flags[t][pn.index(g)]
                else:
                    cands = [(ratio(g, n), k) for k, n in enumerate(pn) if n not in gts]
                    best = max(cands, default=(0, None))
                    if best[0] >= 0.5:
                        rec["closest"] = preds[t][best[1]]
                        rec["flagged"] = flags[t][best[1]]
                    else:  # VLM missed it entirely; flagged if OCR saw something close
                        rec["flagged"] = any(ratio(g, n) >= 0.5 for n in a_norms[t])
            elif not ok:
                cands = [(ratio(g, NORMALIZERS[t](p)), p) for p in preds.get(t, [])]
                best = max(cands, default=(0, None))
                if best[0] >= 0.5:
                    rec["closest"] = best[1]
            recs.append(rec)
        fps = [p for p, n in zip(preds.get(t, []), pn) if n not in gts and (t, n) not in ignore]
        out[t] = {"gt": recs, "fp": fps}
    return out


def load_runs(data: Path):
    gts = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((data / "gt").glob("*.json"))}
    ocr = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((data / "ocr").glob("*.json"))}
    runs = {}
    for d in sorted((data / "runs").glob("*__*")):
        runs[d.name] = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.json")}
    return gts, ocr, runs


def build_results(data: Path):
    gts, ocr, runs = load_runs(data)
    results = []
    a_preds = {}
    for iid, gt in gts.items():
        base = {k: gt[k] for k in ("image_id", "base_id", "style", "variant", "scenario")}
        if iid in ocr:
            o = ocr[iid]
            preds = extract([l["text"] for l in o["lines"]])
            a_preds[iid] = preds
            om = o["model"]
            label = (f"PaddleOCR {om['paddleocr']} lang={om['lang']} {om.get('ocr_version', '')} "
                     f"det={om.get('det')} rec={om.get('rec')} device={om.get('device')}")
            results.append({**base, "method": "A", "model": label,
                            "config": "A__paddleocr", "pred": preds, "scores": score_strings(gt, preds, None, None),
                            "seconds": o["seconds"], "tokens_in": 0, "tokens_out": 0, "tokens_thought": 0,
                            "ocr_text": [l["text"] for l in o["lines"]]})
    for cfg, recs in runs.items():
        method, model = cfg.split("__", 1)
        for iid, gt in gts.items():
            r = recs.get(iid)
            base = {k: gt[k] for k in ("image_id", "base_id", "style", "variant", "scenario")}
            if r is None:
                results.append({**base, "method": method, "model": model, "config": cfg, "missing": True})
                continue
            preds = vlm_strings(r["output"])
            flags = a_norms = None
            if method == "C":
                a_norms = {t: {NORMALIZERS[t](x) for x in a_preds[iid][t]} for t in TYPES}
                flags = {t: [NORMALIZERS[t](p) not in a_norms[t] for p in preds[t]] for t in TYPES}
            sc = score_strings(gt, preds, flags, a_norms)
            c, n = side_score(gt["messages"], r["output"].get("messages", []))
            row = {**base, "method": method, "model": model, "model_version": r.get("model_version"), "config": cfg,
                   "pred": preds, "scores": sc, "side_correct": c, "side_total": n, "seconds": r["seconds"],
                   "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"], "tokens_thought": r["tokens_thought"]}
            if flags is not None:
                row["khong_chac"] = {t: [p for p, f in zip(preds[t], flags[t]) if f] for t in TYPES}
            results.append(row)
    return results, gts


def pct(k, n):
    return f"{100 * k / n:.1f}" if n else "-"


def agg_exact(rows, t, variant=None):
    k = n = 0
    for r in rows:
        if r.get("missing") or (variant and r["variant"] != variant):
            continue
        for g in r["scores"][t]["gt"]:
            n += 1
            k += g["correct"]
    return k, n


def report(results, gts, out: Path, data: Path, cmd: str):
    by_cfg = defaultdict(list)
    for r in results:
        by_cfg[r["config"]].append(r)
    cfgs = sorted(by_cfg, key=lambda c: ({"A": 0, "B": 1, "C": 2}[c[0]], c))
    L = []
    w = L.append
    w("# E1 - Đọc chuỗi chính xác từ ảnh chụp chat\n")
    w("Câu hỏi: có cần OCR riêng bên cạnh VLM để lấy số tài khoản, số điện thoại, link, số tiền từ ảnh chụp chat tiếng Việt không?\n")
    n_img = len(gts)
    n_str = sum(len(g["strings"][t]) for g in gts.values() for t in TYPES)
    w(f"Dữ liệu: {n_img} ảnh tổng hợp (30 ảnh gốc x 6 biến thể), {n_str} chuỗi cần đọc. "
      "3 kiểu giao diện (giống Zalo / Messenger / SMS) x 5 tình huống. Mọi số, tên, tên miền đều tự sinh ngẫu nhiên.\n")
    missing = {c: sum(1 for r in rows if r.get("missing")) for c, rows in by_cfg.items()}
    if any(missing.values()):
        w(f"Thiếu kết quả (lỗi API sau 6 lần thử, hoặc dừng sớm vì model chậm quá ngưỡng): {missing}\n")

    # Decision
    w("## Kết luận theo quy tắc đề xuất\n")
    decision_lines = []
    for c in cfgs:
        if not c.startswith("B__"):
            continue
        model = c[3:]
        worst = min(((agg_exact(by_cfg[c], t, v), t, v) for t in TYPES for v in VARIANTS),
                    key=lambda x: x[0][0] / x[0][1] if x[0][1] else 1)
        (k, n), wt, wv = worst
        b_ok = all((lambda kn: kn[1] == 0 or kn[0] / kn[1] >= 0.98)(agg_exact(by_cfg[c], t, v))
                   for t in TYPES for v in VARIANTS)
        cc = f"C__{model}"
        gaps = []
        if cc in by_cfg:
            have_c = {r["image_id"] for r in by_cfg[cc] if not r.get("missing")}
            b_common = [r for r in by_cfg[c] if r["image_id"] in have_c]  # same images for a fair B-vs-C gap
            for t in TYPES:
                for v in VARIANTS:
                    kb, nb = agg_exact(b_common, t, v)
                    kc, nc = agg_exact(by_cfg[cc], t, v)
                    if nb and nc:
                        gaps.append((100 * (kc / nc - kb / nb), t, v))
        max_gap = max(gaps, default=(0, None, None))
        c_ok = max_gap[0] <= 2.0
        decision_lines.append((model, b_ok, c_ok if gaps else None, worst, max_gap))
        c_txt = (f"C hơn B nhiều nhất {max_gap[0]:+.1f} điểm % ({TYPE_VI[max_gap[1]]}, {VARIANT_VI[max_gap[2]]}), "
                 f"so trên cùng tập ảnh; <= 2 điểm: {'có' if c_ok else 'không'}" if gaps else "chưa có kết quả C")
        w(f"- **{model}**: B thấp nhất {pct(k, n)}% ({TYPE_VI[wt]}, {VARIANT_VI[wv]}); "
          f"B đạt >=98% ở mọi loại x biến thể: {'có' if b_ok else 'không'}. {c_txt}. "
          f"=> {'bỏ OCR riêng' if b_ok and c_ok and gaps else 'giữ cả hai'}.")
    w("")
    w("{{RECOMMENDATION}}\n")

    # Main table
    w("## 1. Khớp chính xác theo loại chuỗi (gộp 6 biến thể)\n")
    w("Khớp = chuỗi chuẩn hóa của đáp án có trong danh sách model trả về. Chuẩn hóa: số TK bỏ mọi ký tự không phải số; "
      "SĐT bỏ dấu cách/chấm và đổi +84 thành 0; link bỏ `https://`, `www.`, dấu cách, hạ chữ thường phần tên miền, "
      "giữ nguyên phần đường dẫn; số tiền bỏ dấu cách và dấu phân cách nghìn, giữ đơn vị (`30.000đ` = `30000đ`, "
      "`2tr5` khác `2.500.000đ`). Ngoặc là khoảng tin cậy 95% (Wilson).\n")
    w("| Cách | Model | " + " | ".join(TYPE_VI[t] for t in TYPES) + " | Tất cả |")
    w("|---|---|" + "---|" * (len(TYPES) + 1))
    for c in cfgs:
        rows = by_cfg[c]
        cells, K, N = [], 0, 0
        for t in TYPES:
            k, n = agg_exact(rows, t)
            K, N = K + k, N + n
            lo, hi = wilson(k, n)
            cells.append(f"{pct(k, n)}% ({k}/{n}) [{100 * lo:.0f}-{100 * hi:.0f}]")
        w(f"| {c[0]} | {c.split('__', 1)[1]} | " + " | ".join(cells) + f" | {pct(K, N)}% |")
    w("")
    w("Link tách đôi: **tên miền** = phần trước dấu `/` đầu tiên, hạ chữ thường; **đường dẫn** = phần còn lại, "
      "phân biệt hoa thường. Đúng khi model trả về ít nhất một link có phần đó trùng từng ký tự.\n")
    w("| Cách | Model | Link nguyên chuỗi | Tên miền | Đường dẫn |")
    w("|---|---|---|---|---|")
    for c in cfgs:
        gl = [g for r in by_cfg[c] if not r.get("missing") for g in r["scores"]["link"]["gt"]]
        k, kd, kp, n = (sum(g["correct"] for g in gl), sum(g["domain_ok"] for g in gl),
                        sum(g["path_ok"] for g in gl), len(gl))
        w(f"| {c[0]} | {c.split('__', 1)[1]} | {pct(k, n)}% ({k}/{n}) | {pct(kd, n)}% ({kd}/{n}) | "
          f"{pct(kp, n)}% ({kp}/{n}) |")
    w("")

    w("## 2. Khớp chính xác theo biến thể\n")
    w("Mỗi ô: % khớp (số đúng/tổng). Mỗi biến thể có 30 ảnh, khoảng 30 chuỗi mỗi loại: một lỗi = khoảng 3,3 điểm %.\n")
    w("| Cách | Model | Biến thể | " + " | ".join(TYPE_VI[t] for t in TYPES) + " |")
    w("|---|---|---|" + "---|" * len(TYPES))
    for c in cfgs:
        for v in VARIANTS:
            cells = []
            for t in TYPES:
                k, n = agg_exact(by_cfg[c], t, v)
                cells.append(f"{pct(k, n)} ({k}/{n})")
            w(f"| {c[0]} | {c.split('__', 1)[1]} | {VARIANT_VI[v]} | " + " | ".join(cells) + " |")
    w("")

    w("## 3. Chuỗi thừa và số tiền theo giá trị\n")
    w("Chuỗi thừa = model trả về chuỗi không có trong đáp án (đọc sai cũng tính một chuỗi thừa). "
      "Số tiền theo giá trị = quy ra số đồng rồi so (`2tr5` = `2.500.000đ`), để thấy lỗi nào chỉ là đổi định dạng. "
      "Link khi coi `I` = `l`: hai chữ này gần như trùng nét trong font không chân (Arial, Noto Sans) mà app chat dùng.\n")
    w("| Cách | Model | " + " | ".join(f"Thừa {TYPE_VI[t]}" for t in TYPES)
      + " | Số tiền khớp giá trị | Link khớp khi coi I = l |")
    w("|---|---|" + "---|" * (len(TYPES) + 2))
    for c in cfgs:
        rows = [r for r in by_cfg[c] if not r.get("missing")]
        fps = [sum(len(r["scores"][t]["fp"]) for r in rows) for t in TYPES]
        vk = sum(g["value_ok"] for r in rows for g in r["scores"]["amount"]["gt"])
        vn = sum(1 for r in rows for g in r["scores"]["amount"]["gt"])
        lk = sum(g["il_ok"] for r in rows for g in r["scores"]["link"]["gt"])
        ln = sum(1 for r in rows for g in r["scores"]["link"]["gt"])
        w(f"| {c[0]} | {c.split('__', 1)[1]} | " + " | ".join(map(str, fps)) + f" | {pct(vk, vn)}% ({vk}/{vn}) | "
          f"{pct(lk, ln)}% ({lk}/{ln}) |")
    w("")

    w("## 4. Cờ `khong_chac` của cách C\n")
    w("Cờ bật khi chuỗi VLM trả về không trùng (sau chuẩn hóa) với chuỗi nào regex lấy từ OCR. Với chuỗi VLM bỏ sót, "
      "tính là có cờ nếu OCR có một chuỗi cùng loại gần giống (tỉ lệ giống >= 0,5).\n")
    w("| Model | Chuỗi đọc sai được gắn cờ | Chuỗi đọc đúng bị gắn cờ nhầm | Theo loại: sai được gắn cờ / đúng bị gắn nhầm |")
    w("|---|---|---|---|")
    for c in cfgs:
        if not c.startswith("C__"):
            continue
        rows = [r for r in by_cfg[c] if not r.get("missing")]
        per = []
        tw = tf = cw = cf = 0
        for t in TYPES:
            gs = [g for r in rows for g in r["scores"][t]["gt"]]
            wrong = [g for g in gs if not g["correct"]]
            right = [g for g in gs if g["correct"]]
            fw = sum(g["flagged"] for g in wrong)
            fr = sum(g["flagged"] for g in right)
            tw, tf, cw, cf = tw + len(wrong), tf + fw, cw + len(right), cf + fr
            per.append(f"{TYPE_VI[t]} {fw}/{len(wrong)}, {fr}/{len(right)}")
        w(f"| {c[3:]} | {pct(tf, tw)}% ({tf}/{tw}) | {pct(cf, cw)}% ({cf}/{cw}) | {'; '.join(per)} |")
    w("")

    w("## 5. OCR cứu được gì\n")
    w("Với mỗi chuỗi B đọc sai: A (OCR + regex) có đọc đúng không, và C có đọc đúng không.\n")
    w("| Model | Loại | B sai | trong đó A đúng | trong đó C đúng | C sai mà B đúng | Biến thể có chuỗi C cứu được |")
    w("|---|---|---|---|---|---|---|")
    a_rows = {r["image_id"]: r for r in by_cfg.get("A__paddleocr", [])}
    rescue_summary = []
    for c in cfgs:
        if not c.startswith("B__"):
            continue
        model = c[3:]
        c_rows = {r["image_id"]: r for r in by_cfg.get(f"C__{model}", []) if not r.get("missing")}
        for t in TYPES:
            bw = aw = cw_ = cb = 0
            vs = defaultdict(int)
            for r in by_cfg[c]:
                if r.get("missing"):
                    continue
                cr = c_rows.get(r["image_id"])
                ar = a_rows.get(r["image_id"])
                for i, g in enumerate(r["scores"][t]["gt"]):
                    c_ok = cr is not None and cr["scores"][t]["gt"][i]["correct"]
                    if not g["correct"]:
                        bw += 1
                        aw += bool(ar and ar["scores"][t]["gt"][i]["correct"])
                        if c_ok:
                            cw_ += 1
                            vs[VARIANT_VI[r["variant"]]] += 1
                    elif cr is not None and not c_ok:
                        cb += 1
            w(f"| {model} | {TYPE_VI[t]} | {bw} | {aw} | {cw_} | {cb} | "
              + (", ".join(f"{v} ({k})" for v, k in sorted(vs.items(), key=lambda x: -x[1])) or "-") + " |")
            rescue_summary.append((model, t, bw, aw, cw_, cb, dict(vs)))
    w("")

    w("## 6. Phía gửi (trái/phải)\n")
    w("Ghép tin nhắn đáp án với tin nhắn model trả về theo độ giống chữ (>= 0,5), đúng khi ghép được và cùng phía. "
      "Ảnh cắt mép: tin nhắn bị cắt dở không tính.\n")
    w("| Cách | Model | " + " | ".join(VARIANT_VI[v] for v in VARIANTS) + " | Tất cả |")
    w("|---|---|" + "---|" * (len(VARIANTS) + 1))
    for c in cfgs:
        if c.startswith("A__"):
            continue
        rows = [r for r in by_cfg[c] if not r.get("missing")]
        cells = []
        for v in VARIANTS:
            k = sum(r["side_correct"] for r in rows if r["variant"] == v)
            n = sum(r["side_total"] for r in rows if r["variant"] == v)
            cells.append(f"{pct(k, n)}")
        k = sum(r["side_correct"] for r in rows)
        n = sum(r["side_total"] for r in rows)
        w(f"| {c[0]} | {c.split('__', 1)[1]} | " + " | ".join(cells) + f" | {pct(k, n)}% ({k}/{n}) |")
    w("")

    w("## 7. Thời gian và chi phí mỗi ảnh\n")
    w("Giây = thời gian gọi API (gồm mạng) hoặc thời gian OCR một ảnh sau khi nạp model. Token ra gồm token suy nghĩ. "
      "Giá USD/1M token (vào/ra) đọc ngày 2026-11-20 tại aistudio.google.com/docs/latest-model và "
      "ai.google.dev/gemini-api/docs/pricing: gemini-3.5-flash-lite 0,30/2,50; gemini-3.8-flash 0,75/3,75 "
      "(giá giới thiệu tới 31/12/2026, sau đó 1,50/7,50); gemini-4-carbon 2,00/10,00 (giá giới thiệu, "
      "**tăng lên 4,00/20,00 từ 01/12/2026**, tức chi phí bảng dưới nhân đôi). "
      "Cách C = gọi VLM có kèm chữ OCR; cộng thêm thời gian OCR của A nếu chạy nối tiếp.\n")
    w("| Cách | Model | Giây TB | Giây p50 | Giây p90 | Token vào TB | Token ra TB (trong đó suy nghĩ) | USD/ảnh | USD/1000 ảnh |")
    w("|---|---|---|---|---|---|---|---|---|")
    for c in cfgs:
        rows = [r for r in by_cfg[c] if not r.get("missing")]
        secs = sorted(r["seconds"] for r in rows)
        if not secs:
            continue
        ti = sum(r["tokens_in"] for r in rows) / len(rows)
        to = sum(r["tokens_out"] + r["tokens_thought"] for r in rows) / len(rows)
        tt = sum(r["tokens_thought"] for r in rows) / len(rows)
        model = c.split("__", 1)[1]
        pin, pout = PRICES.get(model, (0, 0))
        usd = (ti * pin + to * pout) / 1e6
        w(f"| {c[0]} | {model} | {sum(secs) / len(secs):.2f} | {secs[len(secs) // 2]:.2f} | "
          f"{secs[int(len(secs) * 0.9)]:.2f} | {ti:.0f} | {to:.0f} ({tt:.0f}) | {usd:.5f} | {1000 * usd:.2f} |")
    w("")

    # Examples
    w("## 8. Năm ví dụ đọc sai điển hình\n")
    ex_dir = out / "examples"
    ex_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    for c in cfgs:
        for r in by_cfg[c]:
            if r.get("missing"):
                continue
            for t in TYPES:
                for g in r["scores"][t]["gt"]:
                    if not g["correct"]:
                        errors.append((c, r, t, g))
    # Five errors, most diverse first: distinct (config, type), then distinct underlying string per config.
    errors.sort(key=lambda e: e[3]["il_ok"])  # stable: errors not explained by I/l confusion first
    picked, seen = [], set()
    for keyf in (lambda e: (e[0], e[2]), lambda e: (e[0], e[1]["base_id"], e[2])):
        for e in errors:
            k = keyf(e)
            uid = (e[0], e[1]["base_id"], e[2], e[3]["gt"])
            if len(picked) < 5 and k not in seen and uid not in {(p[0], p[1]["base_id"], p[2], p[3]["gt"]) for p in picked}:
                picked.append(e)
                seen.add(k)
    for i, (c, r, t, g) in enumerate(picked, 1):
        man = next(json.loads(l) for l in open(data / "manifest.jsonl", encoding="utf-8")
                   if json.loads(l)["image_id"] == r["image_id"])
        src = data / man["path"]
        dst = ex_dir / src.name
        shutil.copy(src, dst)
        got = g.get("closest")
        w(f"**{i}. {c[0]} / {c.split('__', 1)[1]} - {TYPE_VI[t]}, ảnh `{r['image_id']}` ({VARIANT_VI[r['variant']]})**\n")
        w(f"![{r['image_id']}](examples/{src.name})\n")
        w(f"- Đáp án: `{g['gt']}`")
        w(f"- Kết quả: {'`' + got + '`' if got else 'bỏ sót'}; mọi chuỗi {TYPE_VI[t]} model trả về: "
          f"{', '.join('`' + p + '`' for p in r['pred'][t]) or '(không có)'}")
        if "flagged" in g:
            w(f"- Cờ `khong_chac`: {'có' if g['flagged'] else 'không'}")
        if c.startswith("A__"):
            near = [l for l in r["ocr_text"] if any(ch.isdigit() for ch in l) or "." in l][:6]
            w(f"- Dòng OCR liên quan: {' / '.join('`' + l + '`' for l in near)}")
        w("")

    # Recommendation (rule from docs/tasks/E1-doc-anh-chat.md)
    passing = [d[0] for d in decision_lines if d[1] and d[2]]
    failing = [d[0] for d in decision_lines if not (d[1] and d[2])]
    rec = []
    if passing and not failing:
        rec.append("**Đề xuất: bỏ OCR riêng.** Cách B đạt >=98% ở cả bốn loại chuỗi trên mọi biến thể và C không hơn B quá 2 điểm %.")
    elif passing:
        rec.append(f"**Đề xuất: bỏ OCR riêng chỉ khi dùng {', '.join(passing)}; với {', '.join(failing)} giữ cả hai.**")
    else:
        rec.append("**Đề xuất: giữ cả OCR riêng và VLM** (cách B không qua quy tắc với model nào).")
    for model, t, bw, aw, cw_, cb, vs in rescue_summary:
        if model in failing and (cw_ or aw):
            where = ", ".join(f"{v} ({k})" for v, k in sorted(vs.items(), key=lambda x: -x[1])) or "-"
            rec.append(f"- {model}, {TYPE_VI[t]}: B sai {bw}; A (OCR) đúng {aw} trong số đó; C sửa được {cw_}, "
                       f"ở biến thể: {where}; C làm hỏng {cb} chuỗi B vốn đúng.")
    text = "\n".join(L).replace("{{RECOMMENDATION}}", "\n".join(rec))

    # Models and versions
    M = ["", "## 9. Model và phiên bản\n"]
    env = data / "env.json"
    if env.exists():
        e = json.loads(env.read_text(encoding="utf-8"))
        M.append("Môi trường chạy (server): " + ", ".join(f"{k}={v}" for k, v in e.items()) + "\n")
    for c in cfgs:
        rows = [r for r in by_cfg[c] if not r.get("missing")]
        if c.startswith("A__"):
            M.append(f"- A: {rows[0]['model']}, enable_mkldnn=False; regex `e1/extract.py`")
        else:
            vers = sorted({str(r.get('model_version')) for r in rows})
            M.append(f"- {c[0]}: `{c.split('__', 1)[1]}`, model_version trả về: {', '.join(vers)}; "
                     "structured output (response_json_schema), nhiệt độ và mức suy nghĩ mặc định")
    # Automatic interpretation: where the errors are, and how many link errors are only I/l confusion
    interp, short = [], []
    for c in cfgs:
        rows = [r for r in by_cfg[c] if not r.get("missing")]
        errs = {t: [g for r in rows for g in r["scores"][t]["gt"] if not g["correct"]] for t in TYPES}
        il = sum(g["il_ok"] for g in errs["link"])
        parts = ", ".join(f"{TYPE_VI[t]} {len(errs[t])}" for t in TYPES)
        interp.append(f"- {c[0]} / {c.split('__', 1)[1]}: số chuỗi đọc sai: {parts}"
                      + (f"; {il}/{len(errs['link'])} lỗi link chỉ là nhầm I với l" if errs["link"] else "") + ".")
        cells = []
        for t in TYPES:
            k, n = agg_exact(rows, t)
            cells.append(f"{TYPE_VI[t]} {pct(k, n)}%")
        short.append(f"- {c[0]} {c.split('__', 1)[1]} ({len(rows)} ảnh): " + ", ".join(cells))
    notes = Path(__file__).with_name("report_notes.md")
    if notes.exists():
        M += ["", notes.read_text(encoding="utf-8").strip().replace("{{INTERPRETATION}}", "\n".join(interp))]
    M += ["", "## Chạy lại\n", "Từ thư mục `pretransfer-scam-assistant/` trên máy local:\n", "```bash",
          f"{cmd}            # dùng cache: ảnh, OCR, kết quả API đã có thì bỏ qua",
          f"FRESH=1 {cmd}    # xóa data/E1 cả hai phía rồi chạy lại từ đầu",
          "python3 -m e1.score --data data/E1 --out experiments/E1   # chỉ chấm lại", "```",
          "", "Chi tiết từng (ảnh, cách đọc) ở `results.jsonl`: chuỗi trả về, chuỗi đáp án, đúng/sai, cờ, giây, token."]
    summary = ("# E1 tóm tắt\n\nKhớp chính xác (gộp 6 biến thể):\n" + "\n".join(short) + "\n\n" + "\n".join(rec)
               + "\n\nChi tiết: experiments/E1/report.md\n")
    return text + "\n".join(M) + "\n", decision_lines, rescue_summary, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/E1")
    ap.add_argument("--out", default="experiments/E1")
    ap.add_argument("--cmd", default="./run_e1.sh")
    args = ap.parse_args()
    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results, gts = build_results(data)
    with open(out / "results.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    md, decision, rescue, summary = report(results, gts, out, data, args.cmd)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({"decision": decision, "rescue": rescue}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(md[:200])
    for d in decision:
        print("decision", d)


if __name__ == "__main__":
    main()
