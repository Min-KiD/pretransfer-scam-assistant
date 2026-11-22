"""Answers for the E4 gen_ref set (E4 task, Phần 4) from the intended strings and two independent read-backs.

Per intended string (data/E1b/gen_ref/intended/<id>.json):
- kept:      gemini-4-carbon (J__gemini-4-carbon) returns it AND it is in the PP-OCRv6 text (spaces, dots, commas
             and line breaks removed; +84 read as 0 for phones);
- auto-fixed: the two readers agree on one other string of that type, close to the intended one (edit distance
             <= max(2, len/4)): the image shows that string, so it becomes the answer;
- review:    anything else; decided by eye in e1/gen_ref_review.json ({"<id>": {"<type>|<intended raw>": "<raw as
             shown>" | null (drop: unreadable/absent), "_add": [{"type", "raw"}], "_drop_image": "why"}}).
Strings both readers return that are not intended (account, phone, link) also go to review: the image model may
have added them. A string of the reference image read back by either reader marks the image as a copy (review).

Writes data/E1b/gen_ref/gt/<id>.json for every image whose strings are all decided, review_queue.md (open items)
and review_summary.json.  Usage: python -m e1.gen_ref_gt
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from e1.scenarios import NORMALIZERS
from e1.score import TYPES, vlm_strings
from e1.score_e1b import _lev

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data/E1b/gen_ref"
REAL = ROOT / "data/E1b/real/gt"
READER, OCR = "J__gemini-4-carbon", "T__pp-ocrv6-gpu"
REVIEW = ROOT / "e1/gen_ref_review.json"


def squash(s: str, fold: bool = False) -> str:
    """lower-case, no spaces/dots/commas; a wrapped hyphen often comes out of OCR as '='. fold: I=l, O=0."""
    s = s.replace("=", "-")
    if fold:
        s = s.replace("I", "l")
    s = re.sub(r"[\s.,]", "", s.lower())
    return s.replace("o", "0") if fold else s


def in_ocr(t: str, raw: str, lines: list[str], fold: bool = False) -> bool:
    """raw is in the OCR text, inside one line, across consecutive lines, or split over two lines (a wrapped
    string with a timestamp line read in between)."""
    k = squash(raw, fold)
    sq = [squash(x, fold) for x in lines]
    if t == "phone":
        k, sq = k.replace("+84", "0"), [x.replace("+84", "0") for x in sq]
    if t == "link":
        k = re.sub(r"^https?://", "", k)
    if not k:
        return False
    if k in "".join(sq):
        return True
    return any(a.endswith(k[:p]) and b.startswith(k[p:])
               for p in range(3, len(k) - 1) for i, a in enumerate(sq) for j, b in enumerate(sq) if i != j)


def main():
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}
    (D / "gt").mkdir(exist_ok=True)
    stats = {"images": 0, "written": 0, "open_images": 0, "dropped_images": 0, "strings": 0, "kept": 0,
             "auto_fixed": 0, "reviewed_fixed": 0, "reviewed_kept": 0, "reviewed_dropped": 0, "added": 0,
             "open_strings": 0, "copy_flags": 0, "missing_reads": 0}
    queue = []
    for p in sorted((D / "intended").glob("*.json")):
        iid = p.stem
        if not any((D / "images").glob(f"{iid}.*")):
            continue
        stats["images"] += 1
        it = json.loads(p.read_text(encoding="utf-8"))
        rp, op = D / "runs" / READER / f"{iid}.json", D / "runs" / OCR / f"{iid}.json"
        if not (rp.exists() and op.exists()):
            stats["missing_reads"] += 1
            continue
        rec = json.loads(rp.read_text(encoding="utf-8"))
        c4 = vlm_strings(rec["output"]) if rec.get("output") else {t: [] for t in TYPES}
        lines = [x["text"] for x in json.loads(op.read_text(encoding="utf-8")).get("lines", [])]
        blob = squash("".join(lines))
        rv = review.get(iid, {})
        if "_drop_image" in rv:
            stats["dropped_images"] += 1
            (D / "gt" / f"{iid}.json").unlink(missing_ok=True)
            continue
        out = {t: [] for t in TYPES}
        open_items, used = [], {t: set() for t in TYPES}
        for t in TYPES:
            c4n = {NORMALIZERS[t](x): x for x in c4.get(t, [])}
            for e in it["strings"][t]:
                stats["strings"] += 1
                key = f"{t}|{e['raw']}"
                if key in rv:  # decided by eye
                    v = rv[key]
                    if v is None:
                        stats["reviewed_dropped"] += 1
                    else:
                        out[t].append({"raw": v, "norm": NORMALIZERS[t](v), "src": "review"})
                        stats["reviewed_kept" if v == e["raw"] else "reviewed_fixed"] += 1
                        used[t].add(NORMALIZERS[t](v))
                    continue
                # 4-carbon returns exactly the intended string; OCR must show it too, I/l and O/0 folded
                # (OCR confuses those, E1), so the look-alike glyph itself rests on 4-carbon
                if e["norm"] in c4n and (in_ocr(t, e["raw"], lines) or in_ocr(t, e["raw"], lines, fold=True)):
                    strict = in_ocr(t, e["raw"], lines)
                    out[t].append({"raw": e["raw"], "norm": e["norm"], "src": "auto" if strict else "auto_fold"})
                    stats["kept" if strict else "kept_fold"] = stats.get("kept" if strict else "kept_fold", 0) + 1
                    used[t].add(e["norm"])
                    continue
                near = [(_lev(n, e["norm"]), n) for n in c4n if n not in used[t]]
                near = [x for x in sorted(near) if x[0] <= max(2, len(e["norm"]) // 4)]
                if near and in_ocr(t, c4n[near[0][1]], lines):
                    raw = c4n[near[0][1]]
                    if raw.replace("I", "l") == e["raw"].replace("I", "l"):
                        # only I vs l differs: the two glyphs are identical in sans-serif chat fonts, so the
                        # image cannot contradict the intended character
                        out[t].append({"raw": e["raw"], "norm": e["norm"], "src": "auto_fold", "read": raw})
                        stats["kept_fold"] = stats.get("kept_fold", 0) + 1
                        used[t].add(e["norm"])
                        continue
                    out[t].append({"raw": raw, "norm": near[0][1], "src": "auto_fix", "intended": e["raw"]})
                    stats["auto_fixed"] += 1
                    used[t].add(near[0][1])
                    continue
                open_items.append((key, f"4-carbon: {sorted(c4n.values()) or '-'}; trong OCR: "
                                        f"{in_ocr(t, e['raw'], lines)} (gộp I/l, O/0: "
                                        f"{in_ocr(t, e['raw'], lines, fold=True)})"))
            if t != "amount":  # strings both readers see that nobody intended
                seen = {u.replace("I", "l") for u in used[t]}
                for n, x in c4n.items():
                    if n.replace("I", "l") not in seen and in_ocr(t, x, lines) and f"{t}|+{x}" not in rv:
                        open_items.append((f"{t}|+{x}", "chuỗi lạ: cả hai cùng đọc, không có trong dự định"))
        for a in rv.get("_add", []):
            out[a["type"]].append({"raw": a["raw"], "norm": NORMALIZERS[a["type"]](a["raw"]), "src": "review"})
            stats["added"] += 1
        ref = json.loads((REAL / f"{it['ref']}.json").read_text(encoding="utf-8"))
        ref_norms = {(t, NORMALIZERS[t](e["raw"] if isinstance(e, dict) else e))
                     for t in TYPES for e in (ref.get("strings") or {}).get(t, [])}
        copied = [n for t, n in ref_norms if len(n) >= 6 and (n in {NORMALIZERS[t](x) for x in c4.get(t, [])}
                                                               or (t != "amount" and n in blob))]
        if copied and "_copy_ok" not in rv:
            stats["copy_flags"] += 1
            open_items.append(("_copy", f"chuỗi của ảnh mẫu {it['ref']}: {copied}"))
        if open_items:
            stats["open_images"] += 1
            stats["open_strings"] += sum(k != "_copy" for k, _ in open_items)
            queue.append((iid, it["ref"], open_items))
            (D / "gt" / f"{iid}.json").unlink(missing_ok=True)
            continue
        gt = {k: it[k] for k in ("image_id", "base_id", "style", "scenario", "variant", "ref")}
        gt.update(strings=out, messages=[], ignore={"strings": [], "messages": []})
        (D / "gt" / f"{iid}.json").write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
        stats["written"] += 1
    L = ["# gen_ref: chuỗi cần xem bằng mắt\n", "Ghi quyết định vào `e1/gen_ref_review.json`.\n"]
    for iid, ref, items in queue:
        L.append(f"## {iid} (mẫu {ref})")
        L += [f"- `{k}`: {why}" for k, why in items]
        L.append("")
    (D / "review_queue.md").write_text("\n".join(L), encoding="utf-8")
    (D / "review_summary.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
