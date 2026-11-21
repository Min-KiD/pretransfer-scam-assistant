"""Methods B and C: Gemini structured extraction from a chat screenshot.

B: image only.  C: image + PaddleOCR text lines (from e1.ocr_paddle) in the prompt.
Usage: python -m e1.vlm --set E1|E1b|gen|web --model gemini-3.5-flash-lite --method B|C [--workers 8]
Writes <RUN_DIRS[set]>/<method>__<model>/<image_id>.json (resumable: existing files are skipped).
The API key is read from .env (GEMINI_API_KEY) and never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Image sets: input dir (gt/, images/, optional manifest.jsonl) and where model outputs go. data/E1b/real is filled
# by the planner tab, so web outputs live outside it.
SET_DIRS = {"E1": "data/E1", "E1b": "data/E1b", "gen": "data/E1b/gen", "web": "data/E1b/real"}
RUN_DIRS = {"E1": "data/E1/runs", "E1b": "data/E1b/runs", "gen": "data/E1b/gen/runs", "web": "data/E1b/web_runs"}


def set_items(d: Path, s: str):
    """manifest.jsonl rows, or (no manifest) one row per gt/<id>.json that has a matching images/<id>.*"""
    if (d / "manifest.jsonl").exists():
        return [json.loads(l) for l in open(d / "manifest.jsonl", encoding="utf-8")]
    items = []
    for g in sorted((d / "gt").glob("*.json")) if (d / "gt").exists() else []:
        img = next((d / "images").glob(f"{g.stem}.*"), None)
        if img:
            v = json.loads(g.read_text(encoding="utf-8")).get("variant") or s
            items.append({"image_id": g.stem, "variant": v, "path": f"images/{img.name}"})
    return items

SCHEMA = {
    "type": "object",
    "properties": {
        "messages": {
            "type": "array",
            "description": "Every chat bubble visible in the screenshot, top to bottom.",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer", "description": "0-based position from top"},
                    "side": {"type": "string", "enum": ["left", "right"],
                             "description": "left = bubble from the other person, right = bubble from the phone owner"},
                    "text": {"type": "string", "description": "Bubble text exactly as shown, without the timestamp"},
                },
                "required": ["order", "side", "text"],
            },
        },
        "accounts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string", "description": "Bank account number exactly as written"},
                    "bank": {"type": ["string", "null"]},
                    "holder": {"type": ["string", "null"]},
                },
                "required": ["number", "bank", "holder"],
            },
        },
        "phones": {"type": "array", "items": {"type": "string"}, "description": "Phone numbers exactly as written"},
        "links": {"type": "array", "items": {"type": "string"}, "description": "URLs / domains exactly as written"},
        "amounts": {"type": "array", "items": {"type": "string"},
                    "description": "Money amounts exactly as written, including the unit (đ, VND, k, tr...)"},
    },
    "required": ["messages", "accounts", "phones", "links", "amounts"],
}

PROMPT = """Đây là ảnh chụp màn hình một đoạn chat tiếng Việt trên điện thoại.
Trích xuất theo schema:
- messages: mọi bong bóng chat nhìn thấy, từ trên xuống. side = "left" nếu bong bóng nằm bên trái (người kia gửi), "right" nếu bên phải (chủ máy gửi). Bỏ giờ gửi.
- accounts, phones, links, amounts: mọi số tài khoản ngân hàng, số điện thoại, đường link/tên miền, số tiền xuất hiện trong các tin nhắn.

Quy tắc bắt buộc cho các chuỗi:
- Chép NGUYÊN VĂN từng ký tự như trong ảnh, giữ nguyên dấu cách, dấu chấm, chữ hoa/thường, tiền tố (https://, +84) và đơn vị tiền (đ, VND, k, tr).
- KHÔNG sửa lỗi chính tả, KHÔNG đổi định dạng, KHÔNG đoán cho "hợp lý". Link có thể cố tình giả dạng (ví dụ 0 thay o, 1 thay l, rn thay m): chép đúng ký tự nhìn thấy.
- Chuỗi bị cắt mất một phần ở mép ảnh thì bỏ qua.
- Không có thì để mảng rỗng."""

PROMPT_OCR = """

Dưới đây là chữ do một OCR riêng đọc được từ chính ảnh này, theo thứ tự từ trên xuống. OCR có thể đọc sai ký tự, sai dấu, hoặc tách/gộp dòng. Ảnh là nguồn đúng: dùng chữ OCR để soát lại từng ký tự của các chuỗi, nhưng khi OCR và ảnh khác nhau thì chép theo ảnh.
<ocr>
{ocr}
</ocr>"""


def load_key(root: Path) -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    for line in (root / ".env").read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("GEMINI_API_KEY missing from environment and .env")


def call(client, model: str, img: bytes, mime: str, prompt: str, types):
    # Default temperature/thinking level on purpose: Gemini 3+ docs advise against lowering temperature.
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=SCHEMA)
    for attempt in range(6):
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=model, contents=[types.Part.from_bytes(data=img, mime_type=mime), prompt], config=cfg)
            dt = time.perf_counter() - t0
            u = resp.usage_metadata
            parsed = json.loads(resp.text)
            return {"output": parsed, "seconds": round(dt, 3), "model_version": resp.model_version,
                    "tokens_in": u.prompt_token_count, "tokens_out": (u.candidates_token_count or 0),
                    "tokens_thought": (u.thoughts_token_count or 0), "attempts": attempt + 1}
        except Exception as e:  # retry rate limits, 5xx and the odd malformed JSON
            msg = f"{type(e).__name__}: {str(e)[:200]}"
            if attempt == 5:
                return {"error": msg, "attempts": attempt + 1}
            time.sleep(min(60, 2 ** attempt * 3) + random.random() * 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/E1", help="set dir with manifest.jsonl (E1 scripts); --set overrides")
    ap.add_argument("--set", choices=list(SET_DIRS), help="named set: inputs from SET_DIRS, outputs to RUN_DIRS")
    ap.add_argument("--model", required=True)
    ap.add_argument("--method", choices=["B", "C"], required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-mean-seconds", type=float, default=0,
                    help="stop early (keep what finished) if the mean call time over >=20 calls exceeds this")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    data = Path(SET_DIRS[args.set] if args.set else args.data)
    out = Path(RUN_DIRS[args.set] if args.set else data / "runs") / f"{args.method}__{args.model}"
    out.mkdir(parents=True, exist_ok=True)

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=load_key(root))

    manifest = set_items(data, args.set or data.name)
    if args.limit:
        manifest = manifest[: args.limit]
    todo = [m for m in manifest if not (out / f"{m['image_id']}.json").exists()]

    def work(m):
        path = data / m["path"]
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower(), "image/png")
        prompt = PROMPT
        if args.method == "C":
            ocr = json.loads((data / "ocr" / f"{m['image_id']}.json").read_text(encoding="utf-8"))
            prompt += PROMPT_OCR.format(ocr="\n".join(l["text"] for l in ocr["lines"]))
        rec = call(client, args.model, path.read_bytes(), mime, prompt, types)
        rec.update(image_id=m["image_id"], method=args.method, model=args.model)
        if "error" not in rec:
            (out / f"{m['image_id']}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return m["image_id"], rec

    errors, secs, stopped = 0, [], False
    with ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(work, m) for m in todo]
        for i, f in enumerate(as_completed(futs), 1):
            iid, rec = f.result()
            if "error" in rec:
                errors += 1
                print("ERR", iid, rec["error"], flush=True)
                continue
            secs.append(rec["seconds"])
            if i % 20 == 0 or i == len(todo):
                print(f"{args.method} {args.model} {i}/{len(todo)} last={rec['seconds']}s", flush=True)
            mean = sum(secs) / len(secs)
            if args.max_mean_seconds and len(secs) >= 20 and mean > args.max_mean_seconds and not stopped:
                stopped = True
                print(f"SLOW: mean {mean:.1f}s > {args.max_mean_seconds}s after {len(secs)} calls; "
                      "cancelling the rest, keeping finished results", flush=True)
                for other in futs:
                    other.cancel()
    print("done", args.method, args.model, "errors", errors, "stopped_early", stopped)
    if errors:
        raise SystemExit(f"{errors} calls failed after retries")


if __name__ == "__main__":
    main()
