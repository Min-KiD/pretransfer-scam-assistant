"""Score E1b: open models (+ references A and gemini-3.5-flash-lite) on the E1 set and the E1b hard set.

Usage: python -m e1.score_e1b --root . --out experiments/E1b
Reads data/E1/{gt,ocr,runs}, data/E1b/{gt,real/gt,ocr,runs,open}. Writes report.md, results.jsonl, SUMMARY.md,
examples/ (crops of misread strings on the hard set).
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from e1.extract import extract
from e1.scenarios import NORMALIZERS
from e1.score import TYPES, TYPE_VI, VARIANT_VI, pct, score_strings, side_score, vlm_strings, wilson
from e1.vlm import RUN_DIRS, SET_DIRS

VARIANT_VI = {**VARIANT_VI, "nho33": "thu nhỏ 33%", "nen2": "nén JPEG 2 lần", "chuplai": "chụp lại màn hình",
              "dai": "chat dài", "gen_sua": "gen: sửa thành ảnh chụp", "gen_moi": "gen: sinh từ mô tả",
              "web": "ảnh web thật"}
HARD_VARIANTS = ("nho33", "nen2", "chuplai", "dai")
REPO = {"pp-ocrv6-gpu": "PaddlePaddle/PP-OCRv6_medium_{det,rec}_safetensors",
        "qwen3-vl-8b": "Qwen/Qwen3-VL-8B-Instruct", "qwen3-vl-4b": "Qwen/Qwen3-VL-4B-Instruct",
        "paddleocr-vl-1.6": "PaddlePaddle/PaddleOCR-VL-1.6", "mineru2.5-pro": "opendatalab/MinerU2.5-Pro-2605-1.2B",
        "glm-ocr": "zai-org/GLM-OCR", "gemma-4-e4b": "google/gemma-4-E4B-it"}
SECTION = {"E1": "2", "E1b": "3", "gen": "3b", "web": "3c"}
SET_VI = {"E1": "E1 (180 ảnh dễ)", "E1b": "E1b khó (100 ảnh)", "gen": "gen (ảnh do Nano Banana sinh)",
          "web": "web (ảnh chat thật đăng công khai)"}


def load_json_dir(d: Path):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))} if d.exists() else {}


def empty_preds():
    return {t: [] for t in TYPES}


def normalize_gt(g: dict, set_name: str) -> dict:
    """Hand-made answers (web, gen) may lack messages, ignore, norm or some types: fill them in."""
    if set_name == "web":
        g["variant"] = "web"  # planner files say "real"; one variant per set here
    g.setdefault("variant", set_name)
    g.setdefault("messages", [])
    g.setdefault("ignore", {"strings": [], "messages": []})
    for k in ("base_id", "style", "scenario"):
        g.setdefault(k, None)
    strings = g.setdefault("strings", {})
    for t in TYPES:
        lst = strings.setdefault(t, [])
        for i, e in enumerate(lst):
            if isinstance(e, str):
                e = lst[i] = {"raw": e}
            if not e.get("norm"):
                e["norm"] = NORMALIZERS[t](e["raw"])
    return g


def build(root: Path):
    sets = {}
    for s, d in SET_DIRS.items():
        gts = load_json_dir(root / d / "gt")
        if gts:
            sets[s] = {k: normalize_gt(v, s) for k, v in gts.items()}
    data_dir = {s: root / d for s, d in SET_DIRS.items()}
    results = []

    def add(set_name, gt, cfg, group, model, rec):
        base = {k: gt.get(k) for k in ("image_id", "base_id", "style", "variant", "scenario")}
        row = {**base, "set": set_name, "config": cfg, "group": group, "model": model}
        if rec is None:
            row["missing"] = True
            results.append(row)
            return
        row["seconds"] = rec.get("seconds")
        if group in ("A", "T"):
            if "error" in rec:
                preds, row["run_error"] = empty_preds(), rec["error"]
            else:
                lines = [l["text"] for l in rec["lines"]] if "lines" in rec else rec.get("raw", "").split("\n")
                preds = extract(lines)
                if set_name != "web":  # web images are third-party: results keep only ids and strings
                    row["text"] = "\n".join(lines)
        else:
            out = rec.get("output")
            broken = "error" in rec or out is None or rec.get("parse_error")
            if broken:
                preds = empty_preds()
                row["json_broken"] = rec.get("error") or rec.get("parse_error") or "no output"
                if set_name != "web":
                    row["raw"] = (rec.get("raw") or "")[:2000]
            else:
                preds = vlm_strings(out)
            c, n = side_score(gt["messages"], [] if broken else out.get("messages", []))
            row.update(side_correct=c, side_total=n)
            for k in ("tokens_in", "tokens_out", "tokens_thought"):
                if k in rec:
                    row[k] = rec[k]
        row["pred"] = preds
        row["scores"] = score_strings(gt, preds, None, None)
        results.append(row)

    for s, gts in sets.items():
        d = data_dir[s]
        # A: PP-OCRv6 CPU (E1 run, or the E1b CPU fallback)
        ocr = load_json_dir(d / "ocr")
        if ocr:
            for iid, gt in gts.items():
                add(s, gt, "A__pp-ocrv6-cpu", "A", "PP-OCRv6 medium CPU + regex", ocr.get(iid))
        runs_root = root / RUN_DIRS[s]
        for rd in sorted(runs_root.glob("*__*")) if runs_root.exists() else []:
            prefix, model = rd.name.split("__", 1)
            if prefix == "B" and model != "gemini-3.5-flash-lite":
                continue
            if prefix not in ("B", "T", "J"):
                continue
            recs = load_json_dir(rd)
            group = {"B": "J", "T": "T", "J": "J"}[prefix]
            cfg = rd.name if prefix != "B" else f"J__{model}"
            for iid, gt in gts.items():
                add(s, gt, cfg, group, model, recs.get(iid))
    # A configs that do not exist in a set at all are dropped; partially-run configs keep "missing" rows
    present = defaultdict(set)
    for r in results:
        if not r.get("missing"):
            present[r["set"]].add(r["config"])
    results = [r for r in results if r["config"] in present[r["set"]]]
    return results, sets


def agg(rows, key="correct", t=None, variant=None):
    k = n = 0
    for r in rows:
        if r.get("missing") or (variant and r["variant"] != variant):
            continue
        for tt in ([t] if t else TYPES):
            for g in r["scores"][tt]["gt"]:
                n += 1
                k += bool(g[key])
    return k, n


def link_split(rows, variant=None):
    gl = [g for r in rows if not r.get("missing") and (not variant or r["variant"] == variant)
          for g in r["scores"]["link"]["gt"]]
    return (sum(g["domain_ok"] for g in gl), sum(g["path_ok"] for g in gl), len(gl))


def cell(k, n, ci=False):
    if not n:
        return "-"
    if ci:
        lo, hi = wilson(k, n)
        return f"{pct(k, n)}% ({k}/{n}) [{100 * lo:.0f}-{100 * hi:.0f}]"
    return f"{pct(k, n)} ({k}/{n})"


def speed(rows):
    s = sorted(r["seconds"] for r in rows if not r.get("missing") and r.get("seconds") is not None)
    if not s:
        return None
    return statistics.mean(s), s[len(s) // 2], s[min(len(s) - 1, int(0.9 * len(s)))], len(s)


def label(cfg):
    g, m = cfg.split("__", 1)
    return {"A": "Chữ (ref A)", "T": "Chữ", "J": "JSON"}[g], m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="experiments/E1b")
    args = ap.parse_args()
    root, out = Path(args.root), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results, sets = build(root)
    with open(out / "results.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by = defaultdict(list)
    for r in results:
        by[(r["set"], r["config"])].append(r)
    cfgs = sorted({r["config"] for r in results}, key=lambda c: ({"A": 0, "T": 1, "J": 2}[c[0]], c))
    meta = load_json_dir(root / "data/E1b/open")
    events = []
    ev = root / "data/E1b/open/events.jsonl"
    if ev.exists():
        events = [json.loads(l) for l in ev.read_text(encoding="utf-8").splitlines() if l.strip()]
    final_state = {}
    for e in events:
        final_state.setdefault(e["model"], {}).update(state=e["state"], reason=e["reason"] or final_state.get(
            e["model"], {}).get("reason"))

    L = []
    w = L.append
    w("# E1b - Model mã nguồn mở và bộ ảnh khó\n")
    w("Câu hỏi: trên GPU 16GB (RTX 4060 Ti), model mở nào đọc ảnh chat tiếng Việt ngang hoặc hơn "
      "`gemini-3.5-flash-lite`; OCR nào hơn PP-OCRv6; ảnh khó thì cách đọc nào gãy trước.\n")
    n_hard = len(sets["E1b"])
    n_str = sum(len(g["strings"][t]) for g in sets["E1b"].values() for t in TYPES)
    w(f"Bộ khó: {n_hard} ảnh, {n_str} chuỗi: thu nhỏ 33% (30), nén JPEG q30 -> 70% -> q30 (30), chụp lại màn hình "
      "(30: viền máy và nền bàn, xoay 2-4 độ, méo phối cảnh nhẹ, moiré nhẹ, mờ, nhiễu, JPEG q85), chat dài 20-29 tin "
      "(10 ảnh rộng 1170 px, cao 4122-5316 px). Ba biến thể đầu sinh từ 30 ảnh gốc của E1; đáp án lấy từ lúc sinh.\n")
    w("{{DECISION}}\n")

    # Model status
    w("## 1. Model đã chạy, bị bỏ, và vì sao\n")
    w("| Model | Repo | Trạng thái | Ghi chú |")
    w("|---|---|---|---|")
    for m, st in final_state.items():
        if m in ("env", "pipeline"):
            continue
        w(f"| {m} | {REPO.get(m, '-')} | {st['state']} | {(st.get('reason') or '').replace('|', '/')[:300]} |")
    w("")

    gen_review = root / "data/E1b/gen/review_summary.json"
    gen_review = json.loads(gen_review.read_text(encoding="utf-8")) if gen_review.exists() else None
    for s in sets:
        w(f"## {SECTION[s]}. Xếp hạng trên bộ {SET_VI[s]}\n")
        if s == "gen" and gen_review:
            gr = gen_review
            w(f"{gr['generated']} ảnh sinh bằng `{gr['model']}` (gen_sua: ảnh gốc E1 sửa thành ảnh chụp điện thoại "
              f"cầm tay; gen_moi: sinh từ lời mô tả), {gr['calls']} lần gọi ghi lại, {gr['usd']:.2f} USD. Từng ảnh "
              f"được mở ra xem và so với đáp án dự định (link có 0/O, rn/m, I/l/1 thì cắt phóng to): "
              f"{gr['fixed_images']} ảnh phải sửa đáp án ({gr['fixed_strings']} chuỗi sửa theo đúng chữ ảnh hiện, "
              f"{gr['dropped_strings']} chuỗi không đọc chắc nên bỏ), {gr['dropped_images']} ảnh bị loại; còn "
              f"{len(sets[s])} ảnh, {sum(len(g['strings'][t]) for g in sets[s].values() for t in TYPES)} chuỗi. "
              f"{gr['ambiguous_strings']} link được giữ dù chữ I và l vẽ y hệt nhau trong font của ảnh (ảnh không "
              "mâu thuẫn với đáp án; ảnh E1 cũng vậy). Bộ này không có đáp án phía gửi. Chi tiết từng ảnh: "
              "`e1/gen_review.json`.\n")
        if s == "web":
            w(f"{len(sets[s])} ảnh chat thật đã đăng công khai, do tab kế hoạch thu (nguồn: `data/E1b/real/sources.md`, "
              "không commit). Đáp án chỉ có chuỗi, không có phía gửi; số tài khoản ngoài 8-14 chữ số và tên miền "
              "không đường dẫn vẫn chấm như thường (regex bỏ sót tính là sót).\n")
        w("Khớp chính xác từng ký tự sau chuẩn hóa như E1. Tên miền = phần trước `/` đầu tiên (hạ chữ thường); "
          "đường dẫn = phần sau (phân biệt hoa thường). Ngoặc vuông: khoảng tin cậy 95% (Wilson). "
          "Sắp theo tỉ lệ chung.\n")
        w("| Nhóm | Model | Số ảnh | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn | Tất cả | Phía gửi | JSON hỏng |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|")
        rows_s = [(c, by[(s, c)]) for c in cfgs if by.get((s, c))]
        rows_s.sort(key=lambda x: -(lambda kn: kn[0] / kn[1] if kn[1] else 0)(agg(x[1])))
        for c, rows in rows_s:
            g, m = label(c)
            have = [r for r in rows if not r.get("missing")]
            d, p, n = link_split(rows)
            K, N = agg(rows)
            sc = sum(r.get("side_correct", 0) for r in have)
            sn = sum(r.get("side_total", 0) for r in have)
            broken = sum(1 for r in have if r.get("json_broken"))
            errs = sum(1 for r in have if r.get("run_error"))
            w(f"| {g} | {m} | {len(have)}/{len(rows)} | " + " | ".join(
                cell(*agg(rows, t=t), ci=True) for t in ("account", "phone", "amount", "link")) +
              f" | {cell(d, n)} | {cell(p, n)} | {pct(K, N)}% | {cell(sc, sn) if c[0] == 'J' else '-'} | "
              f"{broken if c[0] == 'J' else '-'}{f' (+{errs} lỗi chạy)' if errs else ''} |")
        w("")

    # Per variant on the hard set
    w("## 4. Bộ khó theo biến thể\n")
    w("Mỗi ô: % khớp (đúng/tổng). Biến thể chat dài chỉ có 10 ảnh (khoảng 10 chuỗi mỗi loại: 1 lỗi = 10 điểm %).\n")
    w("| Nhóm | Model | Biến thể | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn |")
    w("|---|---|---|---|---|---|---|---|---|")
    below = []
    for c in cfgs:
        rows = by.get(("E1b", c))
        if not rows:
            continue
        g, m = label(c)
        for v in HARD_VARIANTS:
            cells = []
            for t in ("account", "phone", "amount", "link"):
                k, n = agg(rows, t=t, variant=v)
                cells.append(cell(k, n))
                if n and k / n < 0.9:
                    below.append((f"{g} {m}", v, TYPE_VI[t], pct(k, n)))
            d, p, n = link_split(rows, v)
            for nm, k in (("Tên miền", d), ("Đường dẫn", p)):
                if n and k / n < 0.9:
                    below.append((f"{g} {m}", v, nm, pct(k, n)))
            w(f"| {g} | {m} | {VARIANT_VI[v]} | " + " | ".join(cells) + f" | {cell(d, n)} | {cell(p, n)} |")
    w("")
    if "gen" in sets:
        w("## 4b. Bộ gen theo biến thể\n")
        w("| Nhóm | Model | Biến thể | Số TK | SĐT | Số tiền | Link | Tên miền | Đường dẫn |")
        w("|---|---|---|---|---|---|---|---|---|")
        for c in cfgs:
            rows = by.get(("gen", c))
            if not rows:
                continue
            g, m = label(c)
            for v in ("gen_sua", "gen_moi"):
                d, p, n = link_split(rows, v)
                w(f"| {g} | {m} | {VARIANT_VI[v]} | " + " | ".join(
                    cell(*agg(rows, t=t, variant=v)) for t in ("account", "phone", "amount", "link"))
                  + f" | {cell(d, n)} | {cell(p, n)} |")
        w("")

    # Speed / resources
    w("## 5. Tốc độ và tài nguyên\n")
    w("Giây mỗi ảnh đo sau khi đã nạp model, từng ảnh một (không gộp batch), tính cả tiền xử lý ảnh. Model mở chạy "
      "trên RTX 4060 Ti 16GB; A (CPU) chạy trên CPU 12 nhân của server; Gemini là thời gian gọi API. VRAM đỉnh "
      "của tiến trình đọc bằng NVML (gồm CUDA context); 'torch' là bộ nhớ torch giữ.\n")
    w("| Nhóm | Model | Bộ | Số ảnh | TB (s) | p50 | p90 | VRAM đỉnh (MiB) | Weights (GB) | Nạp model (s) | Dừng vì hết giờ |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in cfgs:
        g, m = label(c)
        for s in sets:
            # extra-set passes write <cfg>__<sets>.json; the main E1+E1b run writes <cfg>.json
            mt = (meta.get(c, {}) if s in ("E1", "E1b") else
                  next((v for k, v in meta.items() if k.startswith(c + "__") and s in (v.get("sets") or [])), {}))
            sp = speed(by.get((s, c), []))
            if not sp:
                continue
            w(f"| {g} | {m} | {s} | {sp[3]} | {sp[0]:.2f} | {sp[1]:.2f} | {sp[2]:.2f} | "
              f"{mt.get('vram_peak_process_mib', '-')} (torch {mt.get('vram_peak_torch_mib', '-')}) | "
              f"{mt['weights_bytes'] / 1e9:.2f} | {mt.get('load_seconds', '-')} | "
              f"{'có' if mt.get('budget_stop') else 'không'} |" if mt else
              f"| {g} | {m} | {s} | {sp[3]} | {sp[0]:.2f} | {sp[1]:.2f} | {sp[2]:.2f} | - | - | - | - |")
    w("")

    # Error examples on the hard set
    w("## 6. Năm ví dụ đọc sai trên bộ khó\n")
    ex, seen = [], set()
    for c in cfgs:
        for r in by.get(("E1b", c), []):
            if r.get("missing"):
                continue
            for t in ("account", "link", "amount", "phone"):
                for gg in r["scores"][t]["gt"]:
                    key = (c, r["variant"])
                    if not gg["correct"] and key not in seen:
                        seen.add(key)
                        ex.append((c, r, t, gg))
    ex.sort(key=lambda x: (x[2] != "account", x[2] != "link", x[1]["variant"]))
    picked, used_v = [], set()
    for e in ex:
        if (e[1]["variant"], e[0]) in used_v or len(picked) >= 5:
            continue
        if any(p[0] == e[0] for p in picked) and len({p[0] for p in picked}) < len({x[0] for x in ex}):
            continue
        picked.append(e)
        used_v.add((e[1]["variant"], e[0]))
    exd = out / "examples"
    exd.mkdir(exist_ok=True)
    for c, r, t, gg in picked:
        g, m = label(c)
        crop = crop_example(root, r, t, gg, exd)
        got = r["pred"][t]
        w(f"- **{m}**, ảnh `{r['image_id']}` ({VARIANT_VI[r['variant']]}), {TYPE_VI[t]}: đáp án `{gg['gt']}`, model trả "
          f"{', '.join(f'`{x}`' for x in got) if got else 'không có chuỗi nào'}"
          + (f"{'; JSON hỏng: ' + r['json_broken'][:120] if r.get('json_broken') else ''}") + (f". Ảnh: `{crop}`" if crop else ""))
    w("")
    for s in ("gen", "web"):
        if s not in sets:
            continue
        w(f"### 6{'b' if s == 'gen' else 'c'}. Ví dụ đọc sai trên bộ {s} (chỉ mã ảnh và chuỗi)\n")
        n_ex = 0
        for c in cfgs:
            for r in by.get((s, c), []):
                if r.get("missing") or n_ex >= 8:
                    continue
                bad = [(t, gg) for t in ("account", "link", "amount", "phone") for gg in r["scores"][t]["gt"]
                       if not gg["correct"]]
                if not bad:
                    continue
                t, gg = bad[0]
                got = r["pred"][t]
                w(f"- **{label(c)[1]}**, `{r['image_id']}`, {TYPE_VI[t]}: đáp án `{gg['gt']}`, model trả "
                  f"{', '.join(f'`{x}`' for x in got) if got else 'không có chuỗi nào'}")
                n_ex += 1
                break  # one example per config
        if not n_ex:
            w("- không có lỗi nào")
        w("")

    # Versions
    w("## 7. Repo, phiên bản và cấu hình\n")
    for c in cfgs:
        g, m = label(c)
        mt = meta.get(c)
        if mt:
            w(f"- {g} `{m}`: {', '.join(mt['repos'])} @ {', '.join(r[:10] for r in mt['revisions'])}; lượng tử: "
              f"{mt['quant']}; giải mã: {mt['decoding']}; trả tọa độ khối chữ: {'có' if mt.get('boxes') else 'không'}; "
              f"prompt: `{mt['prompt'][:80].replace(chr(10), ' ')}{'...' if len(mt['prompt']) > 80 else ''}`; "
              f"{', '.join(f'{k} {v}' for k, v in mt['versions'].items())}")
        elif c.startswith("A__"):
            w(f"- A: PP-OCRv6 medium (det+rec), PaddleOCR 3.7.0, paddlepaddle 3.3.1 CPU, enable_mkldnn=False; regex `e1/extract.py`")
        else:
            w(f"- JSON `{m}`: Gemini API, cùng prompt và schema với E1 cách B, nhiệt độ và mức suy nghĩ mặc định")
    w("")
    notes = Path(__file__).with_name("report_notes_e1b.md")
    if notes.exists():
        w(notes.read_text(encoding="utf-8").strip() + "\n")
    w("## Chạy lại\n")
    w("```bash\n# laptop: sinh bộ khó (Playwright + Chrome), đồng bộ lên server, chạy tách rời\n"
      "python3 -m e1.gen_hard --e1 data/E1 --out data/E1b\n"
      "rsync -a --exclude __pycache__ e1 scripts \"$SERVER:pretransfer-scam-assistant/\" && "
      "rsync -a data/E1b \"$SERVER:pretransfer-scam-assistant/data/\"\n"
      "ssh \"$SERVER\" 'cd pretransfer-scam-assistant && bash scripts/e1b_server_run.sh --detach'\n"
      "./scripts/server_status.sh   # trạng thái + kéo kết quả về (SERVER lấy từ .env)\n"
      "python3 -m e1.score_e1b --root . --out experiments/E1b      # chấm lại\n"
      "# Phần 1b, bộ gen (server, có .env): sinh ảnh, kéo về, duyệt bằng mắt vào e1/gen_review.json, áp đáp án\n"
      "ssh \"$SERVER\" 'cd pretransfer-scam-assistant && .conda/pretransfer/bin/python -m e1.gen_nb'\n"
      "rsync -a \"$SERVER:pretransfer-scam-assistant/data/E1b/gen\" data/E1b/ && python3 -m e1.gen_apply\n"
      "rsync -a data/E1b/gen \"$SERVER:pretransfer-scam-assistant/data/E1b/\"\n"
      "ssh \"$SERVER\" 'cd pretransfer-scam-assistant && SETS=gen bash scripts/e1b_extra_run.sh --detach'\n"
      "# bộ web (ảnh trong data/E1b/real do tab kế hoạch thu), rồi xóa weights\n"
      "rsync -a data/E1b/real \"$SERVER:pretransfer-scam-assistant/data/E1b/\"\n"
      "ssh \"$SERVER\" 'cd pretransfer-scam-assistant && SETS=web FINAL=1 bash scripts/e1b_extra_run.sh --detach'\n```\n")

    # Decision by the rule
    D = ["## Kết luận theo quy tắc đề xuất\n",
         "Đủ dùng = trên bộ E1 đạt >=98% ở số TK, SĐT, số tiền và tên miền, và trung bình <=5 giây/ảnh trên GPU này.\n"]
    best = {}
    summ = []
    for c in cfgs:
        if c.startswith("A__") or c == "J__gemini-3.5-flash-lite":
            continue
        rows = by.get(("E1", c), [])
        if not rows:
            continue
        g, m = label(c)
        accs = {t: agg(rows, t=t) for t in ("account", "phone", "amount")}
        d, p, n = link_split(rows)
        accs["domain"] = (d, n)
        sp = speed(rows)
        fails = [f"{TYPE_VI.get(t, 'Tên miền')} {pct(*kn)}%" for t, kn in accs.items() if kn[1] and kn[0] / kn[1] < 0.98]
        slow = sp and sp[0] > 5
        ok = not fails and not slow and sp is not None
        K, N = agg(rows)
        summ.append((g, m, ok, fails, sp, K / N if N else 0))
        if ok and (g not in best or K / N > best[g][1]):
            best[g] = (m, K / N)
        D.append(f"- {g} `{m}`: {'**đủ dùng**' if ok else 'chưa đủ'}"
                 + (f"; hụt: {', '.join(fails)}" if fails else "")
                 + (f"; chậm: {sp[0]:.1f} s/ảnh" if slow else (f"; {sp[0]:.2f} s/ảnh" if sp else ""))
                 + f" ({len([r for r in rows if not r.get('missing')])}/{len(rows)} ảnh E1).")
    for g in ("Chữ", "JSON"):
        D.append(f"- Tốt nhất nhóm {g}: " + (f"`{best[g][0]}`" if g in best else "không có model nào đủ dùng"))
    D.append("\nBộ khó, biến thể kéo một cách đọc xuống dưới 90%:\n")
    agg_below = defaultdict(list)
    for m, v, t, p_ in below:
        agg_below[m].append(f"{VARIANT_VI[v]} / {t} {p_}%")
    for m, items in agg_below.items():
        if all(x.endswith(" 0.0%") for x in items):
            D.append(f"- {m}: 0% ở mọi biến thể và mọi loại chuỗi (không trích được chuỗi nào)")
        else:
            D.append(f"- {m}: " + "; ".join(items))
    if not agg_below:
        D.append("- không có")
    D.append("\nTỉ lệ khớp chung theo bộ (mọi loại chuỗi gộp lại; link tính nguyên chuỗi; '-' = chưa chạy):\n")
    D.append("| Nhóm | Model | " + " | ".join(sets) + " |")
    D.append("|---|---|" + "---|" * len(sets))
    for c in cfgs:
        g, m = label(c)
        D.append(f"| {g} | {m} | " + " | ".join(
            (lambda kn: f"{pct(*kn)}% ({kn[0]}/{kn[1]})" if kn[1] else "-")(agg(by.get((s, c), []))) for s in sets) + " |")
    D.append("\nỞ chế độ Chữ trên bộ `gen` và `web`, phần lớn chuỗi bị sót có nằm sẵn trong chữ OCR trả về, nhưng quy tắc "
             "trích của E1 (regex) không nhận ra. Số đếm và các dạng bị sót xem mục 8.")
    text = "\n".join(L).replace("{{DECISION}}", "\n".join(D))
    (out / "report.md").write_text(text, encoding="utf-8")
    S = ["# E1b tóm tắt\n", "\n".join(D), "\nChi tiết: experiments/E1b/report.md\n"]
    (out / "SUMMARY.md").write_text("\n".join(S), encoding="utf-8")
    print("\n".join(D))


def crop_example(root: Path, r, t, gg, exd: Path):
    try:
        from PIL import Image
        gt = json.loads((root / "data/E1b/gt" / f"{r['image_id']}.json").read_text(encoding="utf-8"))
        e = next(x for x in gt["strings"][t] if x["raw"] == gg["gt"])
        b = e["boxes"][0]
        img = next((root / "data/E1b/images").glob(f"{r['image_id']}.*"))
        im = Image.open(img)
        pad = 0.6 * (b[3] - b[1])
        c = im.crop((max(0, b[0] - 3 * pad), max(0, b[1] - pad), min(im.width, b[2] + 3 * pad), min(im.height, b[3] + pad)))
        p = exd / f"{r['image_id']}__{t}.png"
        c.save(p)
        return f"experiments/E1b/examples/{p.name}"
    except Exception:
        return None


if __name__ == "__main__":
    main()
