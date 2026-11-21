"""Method A, step 1: run PaddleOCR on every E1 image and cache the text lines.

Usage: python -m e1.ocr_paddle --data data/E1 --device gpu:0|cpu
Writes data/E1/ocr/<image_id>.json : {lines:[{text,score,box}], seconds, model}
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def reading_order(items):
    """Sort boxes top-to-bottom, then left-to-right within a row (rows = overlapping y ranges)."""
    items = sorted(items, key=lambda it: (it["box"][1] + it["box"][3]) / 2)
    rows, cur = [], []
    for it in items:
        if cur and (it["box"][1] + it["box"][3]) / 2 > max(c["box"][3] for c in cur) - 4:
            rows.append(cur)
            cur = []
        cur.append(it)
    if cur:
        rows.append(cur)
    return [it for row in rows for it in sorted(row, key=lambda it: it["box"][0])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/E1")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--ocr-version", default="PP-OCRv6")  # newest family in paddleocr 3.7 that covers Vietnamese
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    data = Path(args.data)
    out = data / "ocr"
    out.mkdir(exist_ok=True)

    from paddleocr import PaddleOCR
    import paddleocr
    # enable_mkldnn=False: paddlepaddle 3.3.1 CPU + oneDNN fails on PP-OCRv6 with
    # "ConvertPirAttribute2RuntimeAttribute not support" (seen on the E1 server).
    ocr = PaddleOCR(lang=args.lang, ocr_version=args.ocr_version, device=args.device, enable_mkldnn=False,
                    use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    det, rec = ocr._get_ocr_model_names(args.lang, args.ocr_version)
    model_info = {"paddleocr": paddleocr.__version__, "lang": args.lang, "ocr_version": args.ocr_version,
                  "det": det, "rec": rec, "device": args.device}
    manifest = [json.loads(l) for l in open(data / "manifest.jsonl", encoding="utf-8")]
    if args.limit:
        manifest = manifest[: args.limit]
    # warm-up so the first timed image does not pay model load / CUDA init
    ocr.predict(str(data / manifest[0]["path"]))
    for m in manifest:
        dst = out / f"{m['image_id']}.json"
        if dst.exists():
            continue
        t0 = time.perf_counter()
        res = ocr.predict(str(data / m["path"]))[0]
        dt = time.perf_counter() - t0
        r = res.json["res"] if "res" in res.json else res.json
        items = [{"text": t, "score": round(float(s), 4), "box": [float(v) for v in b]}
                 for t, s, b in zip(r["rec_texts"], r["rec_scores"], r["rec_boxes"])]
        rec = {"image_id": m["image_id"], "lines": reading_order(items), "seconds": round(dt, 3),
               "model": model_info}
        dst.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        print(m["image_id"], f"{dt:.2f}s", len(items), flush=True)


if __name__ == "__main__":
    main()
