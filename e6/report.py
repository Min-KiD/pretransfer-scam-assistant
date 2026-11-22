"""E6 report from data/E6/preds/<model>.jsonl and experiments/E5/sessions.jsonl -> experiments/E6/report.md.

  python -m e6.report

Pre-declared choices (written before looking at test numbers):
- The classifier used against the LLM is the one with the best val macro-F1 (both input kinds pooled).
- Threshold rule: tau = the smallest of 0.30, 0.35, ..., 0.95 at which that classifier is right on >= 95% of the val
  inputs whose top probability exceeds tau; "disagree" then needs top probability > tau.
- LLM conclusion = its scenario after 3 questions; sessions that end in `chua_du_can_cu` have no conclusion to check
  and are reported apart (not in the M3 denominators).
- M3 (plan section 5): among sessions where the LLM concluded, the classifier disagrees with >= 30% of the wrong
  conclusions and with <= 15% of the right ones.
Real narratives: only aggregate numbers here (no text, no ids).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from e1.score import wilson
from e6.classify import SCEN, scenarios

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/E6"
OUT = ROOT / "experiments/E6"
NAMES = {"c0": "C0 TF-IDF + LR", "c1": "C1 e5-base, không train", "c2": "C2 PhoBERT-base-v2", "c3": "C3 e5-small"}
CHUA_DU = "chua_du_can_cu"


def fmt(k, n):
    if not n:
        return "-"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% ({k}/{n}) [{100 * lo:.0f}-{100 * hi:.0f}]"


def load_preds():
    P = {}
    for p in sorted((DATA / "preds").glob("c*.jsonl")):
        rows = [json.loads(l) for l in open(p, encoding="utf-8")]
        for r in rows:
            r["p"] = np.array(r["probs"])
            r["top"] = SCEN[int(r["p"].argmax())]
            r["conf"] = float(r["p"].max())
        P[p.stem] = rows
    return P


def ece(rows, bins=10):
    conf = np.array([r["conf"] for r in rows])
    ok = np.array([r["top"] == r["label"] for r in rows])
    e, table = 0.0, []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        m = (conf > lo) & (conf <= hi) if b else (conf >= lo) & (conf <= hi)
        if m.sum():
            e += m.sum() / len(rows) * abs(ok[m].mean() - conf[m].mean())
            table.append((f"{lo:.1f}-{hi:.1f}", int(m.sum()), conf[m].mean(), ok[m].mean()))
    return e, table


def macro_f1(rows):
    f = []
    for c in SCEN:
        tp = sum(r["top"] == c and r["label"] == c for r in rows)
        fp = sum(r["top"] == c and r["label"] != c for r in rows)
        fn = sum(r["top"] != c and r["label"] == c for r in rows)
        if tp + fp + fn:
            f.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f)) if f else float("nan")


def pick_tau(val_rows):
    for tau in np.arange(0.30, 0.96, 0.05):
        sel = [r for r in val_rows if r["conf"] > tau]
        if sel and sum(r["top"] == r["label"] for r in sel) / len(sel) >= 0.95:
            return round(float(tau), 2)
    return 0.95


def main():
    scen = scenarios()
    nhom = {s: scen[s].nhom for s in SCEN}
    P = load_preds()
    meta = json.loads((DATA / "models.json").read_text()) if (DATA / "models.json").exists() else {}
    sessions = [json.loads(l) for l in open(ROOT / "experiments/E5/sessions.jsonl", encoding="utf-8")]
    sessions = [r for r in sessions if "preds" in r]
    cost = json.loads((DATA / "cost.json").read_text()) if (DATA / "cost.json").exists() else {}
    sets = sorted({r["set"] for rows in P.values() for r in rows if r["set"].startswith("sim:")})
    L = ["# E6 - Bộ phân loại kịch bản nhỏ làm ý kiến thứ hai\n",
         "Đầu vào là chữ người dùng nói. Hai kiểu: `mo_dau` (chỉ tin mở đầu) và `day_du` (tin mở đầu nối các câu trả "
         "lời, không kèm câu hỏi của trợ lý). Train và val do `gemini-3.5-flash-lite` viết (`sim/e6_data.py`, seed "
         f"20261124, 15 kịch bản x 200 train + 20 val, mỗi tình huống hai kiểu đầu vào; {cost.get('calls', '?')} lần gọi, "
         f"{cost.get('usd', 0):.2f} USD). Nhãn là kịch bản chọn lúc sinh. Không train trên 300 tình huống E5 hay lời kể "
         "thật. Tỉ lệ ghi `tử/mẫu` và khoảng Wilson 95%. Mỗi model chạy một lần.\n"]
    # ---- main table
    L.append("## Độ đúng theo tập\n")
    L.append("`sim` = 300 tình huống E5, chỉ tin mở đầu. `sim:<model>` = cùng 300 tình huống, chữ người dùng trong phiên E5 "
             "của model đó. `real` = lời kể từ vụ việc thật (chỉ tính 11 kịch bản lừa đảo; nhãn `khac` báo riêng).\n")
    L.append("| Model | val | sim (mở đầu) | " + " | ".join(f"`{s}`" for s in sets) + " | real (11 kịch bản) | macro-F1 sim | "
             "ECE sim | ms/câu CPU | Dung lượng |")
    L.append("|---|---|---|" + "---|" * len(sets) + "---|---|---|---|---|")
    best, best_f1 = None, -1
    for m, rows in P.items():
        val = [r for r in rows if r["set"] == "val"]
        sim = [r for r in rows if r["set"] == "sim"]
        real = [r for r in rows if r["set"] == "real" and r["label"] != "khac"]
        acc = lambda rs: fmt(sum(r["top"] == r["label"] for r in rs), len(rs))  # noqa: E731
        vf1 = macro_f1(val)
        if vf1 > best_f1:
            best, best_f1 = m, vf1
        md = meta.get(m, {})
        L.append(f"| {NAMES[m]} | {acc(val)} | {acc(sim)} | "
                 + " | ".join(acc([r for r in rows if r["set"] == s]) for s in sets)
                 + f" | {acc(real)} | {macro_f1(sim):.3f} | {ece(sim)[0]:.3f} | {md.get('cpu_ms_p50', '-')} | "
                 f"{md.get('size_mb') or '-'} MB |")
    L.append(f"\nModel dùng cho phần lệch với LLM (val macro-F1 cao nhất, chọn trước khi xem test): **{NAMES[best]}** "
             f"({best_f1:.3f}).\n")
    # ---- calibration table + false alarms + real khac
    rows = P[best]
    e, tab = ece([r for r in rows if r["set"] == "sim"])
    L.append(f"## Độ khớp xác suất ({NAMES[best]}, sim mở đầu; ECE {e:.3f})\n")
    L.append("| Độ tin | Số mẫu | Độ tin TB | Độ đúng |")
    L.append("|---|---|---|---|")
    for b, n, c, a in tab:
        L.append(f"| {b} | {n} | {c:.2f} | {a:.2f} |")
    L.append("\n## Báo nhầm trên 80 tình huống bình thường của E5\n")
    L.append("Báo nhầm: tình huống bình thường mà bộ phân loại chọn một kịch bản lừa đảo.\n")
    L.append("| Model | sim (mở đầu) | " + " | ".join(f"`{s}`" for s in sets) + " |")
    L.append("|---|---|" + "---|" * len(sets))
    for m, rs in P.items():
        cells = []
        for s in ["sim"] + sets:
            norm = [r for r in rs if r["set"] == s and nhom[r["label"]] != "lua_dao"]
            cells.append(fmt(sum(nhom[r["top"]] == "lua_dao" for r in norm), len(norm)))
        L.append(f"| {NAMES[m]} | " + " | ".join(cells) + " |")
    L.append("\n## Lời kể thật có nhãn `khac` (không thuộc 11 kịch bản lừa đảo)\n")
    L.append("Mong đợi: xác suất cao nhất thấp, không ép vào một kịch bản.\n")
    L.append("| Model | Số lời kể | Xác suất cao nhất TB | Trung vị | Số lời kể có xác suất cao nhất > 0,5 | So: lời kể 11 kịch bản, TB |")
    L.append("|---|---|---|---|---|---|")
    for m, rs in P.items():
        kh = [r["conf"] for r in rs if r["set"] == "real" and r["label"] == "khac"]
        sc = [r["conf"] for r in rs if r["set"] == "real" and r["label"] != "khac"]
        if kh:
            L.append(f"| {NAMES[m]} | {len(kh)} | {np.mean(kh):.2f} | {np.median(kh):.2f} | "
                     f"{sum(c > 0.5 for c in kh)} | {np.mean(sc):.2f} |")
    # ---- confusions of the best model
    L.append(f"\n## Cặp nhầm nhiều nhất ({NAMES[best]})\n")
    for s in ["sim", "real"] + sets[:1]:
        cnt = Counter((r["label"], r["top"]) for r in rows if r["set"] == s and r["top"] != r["label"])
        L.append(f"- `{s}`: " + "; ".join(f"`{a}` -> `{b}` {n}" for (a, b), n in cnt.most_common(6)))
    # ---- disagreement with the LLM
    tau = pick_tau([r for r in rows if r["set"] == "val"])
    L.append(f"\n## Lệch với LLM (bộ phân loại {NAMES[best]}, chữ người dùng trong cùng phiên)\n")
    L.append(f"Ngưỡng cho quy tắc có ngưỡng: tau = {tau} (nhỏ nhất mà trên val bộ phân loại đúng từ 95% số mẫu có xác "
             "suất cao nhất vượt tau).\n")
    verdicts = {}
    for s in sets:
        llm_model = s.split(":", 1)[1]
        sess = {r["case"]: r for r in sessions if r["model"] == llm_model}
        cl = {r["id"]: r for r in rows if r["set"] == s}
        concl = [(sess[c], cl[c]) for c in cl if sess[c]["preds"][-1] != CHUA_DU]
        n_chua = sum(sess[c]["preds"][-1] == CHUA_DU for c in cl)
        L.append(f"### LLM `{llm_model}`\n")
        L.append(f"{len(cl)} phiên; LLM kết luận `{CHUA_DU}` ở {n_chua} phiên (không tính dưới đây).\n")
        for rule, dis in (("lệch bất kể độ tin", lambda c, x: c["top"] != x),
                          (f"lệch khi xác suất cao nhất > {tau}", lambda c, x: c["top"] != x and c["conf"] > tau)):
            wrong = [(se, c) for se, c in concl if se["preds"][-1] != se["kich_ban"]]
            right = [(se, c) for se, c in concl if se["preds"][-1] == se["kich_ban"]]
            cw = sum(dis(c, se["preds"][-1]) for se, c in wrong)
            fr = sum(dis(c, se["preds"][-1]) for se, c in right)
            L.append(f"**Quy tắc {rule}**\n")
            L.append("| | Bộ phân loại cùng kết luận | Bộ phân loại lệch |")
            L.append("|---|---|---|")
            L.append(f"| LLM đúng ({len(right)}) | {len(right) - fr} | {fr} |")
            L.append(f"| LLM sai ({len(wrong)}) | {len(wrong) - cw} | {cw} |\n")
            # "lệch thì hạ xuống chua_du_can_cu"
            def outcome(apply):
                kept = [(se, c) for se, c in concl if not (apply and dis(c, se["preds"][-1]))]
                acc_k = sum(se["preds"][-1] == se["kich_ban"] for se, _ in kept)
                chua = n_chua + (len(concl) - len(kept))
                fp_n = [se for se in sess.values() if nhom[se["kich_ban"]] != "lua_dao"]
                kept_ids = {se["case"] for se, _ in kept}
                fp = sum(se["case"] in kept_ids and se["preds"][-1] in nhom and nhom[se["preds"][-1]] == "lua_dao"
                         for se in fp_n)
                sc = [se for se in sess.values() if nhom[se["kich_ban"]] == "lua_dao"]
                miss = sum(se["case"] in kept_ids and se["preds"][-1] in nhom and nhom[se["preds"][-1]] != "lua_dao"
                           for se in sc)
                return (fmt(acc_k, len(kept)), fmt(chua, len(cl)), fmt(fp, len(fp_n)), fmt(miss, len(sc)))
            L.append("| | Đúng trên phần còn kết luận | `chua_du_can_cu` | Báo nhầm | Bỏ sót |")
            L.append("|---|---|---|---|---|")
            L.append("| Không áp | " + " | ".join(outcome(False)) + " |")
            L.append("| Lệch thì hạ xuống `chua_du_can_cu` | " + " | ".join(outcome(True)) + " |\n")
            ok = len(wrong) and cw / len(wrong) >= 0.30 and (not right or fr / len(right) <= 0.15)
            verdicts[(llm_model, rule)] = bool(ok)
            L.append(f"M3: bắt {fmt(cw, len(wrong))} kết luận sai (cần từ 30%), gắn nhầm {fmt(fr, len(right))} kết luận "
                     f"đúng (cần không quá 15%): **{'đạt' if ok else 'không đạt'}**.\n")
    L.append("## Model và train\n")
    for m, md in meta.items():
        tr = md.get("train", {})
        L.append(f"- {NAMES[m]}: " + ", ".join(f"{k} {v}" for k, v in tr.items() if k != "log")
                 + f"; thiết bị train {md.get('train_device')}; CPU {md.get('cpu_ms_p50')} ms/câu p50 "
                 f"({md.get('cpu_threads')} luồng)")
        for e_ in tr.get("log", []):
            L.append(f"  - epoch {e_['epoch']}: loss train {e_['train_loss']}, val macro-F1 {e_['val_macro_f1']}, "
                     f"val log-loss {e_['val_log_loss']}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("best:", best, "tau:", tau, "M3:", verdicts)
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
