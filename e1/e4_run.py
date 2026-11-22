"""E4: read chat screenshots into e1.vlm.SCHEMA JSON with any core.llm model (Gemini, OpenAI, a local vLLM server).

Modes (the run dir prefix):
  J   image -> JSON, schema as constrained decoding (Gemini, OpenAI, vLLM)
  Ju  image -> JSON, schema only as text in the prompt (vLLM with constrained decoding off)
  O   PP-OCRv6 text lines with their horizontal position -> JSON, no image (answers "is the image needed?")
  JO  image + the same OCR lines in the prompt -> JSON, constrained (phase B3; text from e1.lora_train.user_text,
      identical to its training prompt)

  python -m e1.e4_run --model gemini-3.8-flash@low --mode J --sets web,gen [--workers 6] [--cap-usd 3]
  python -m e1.e4_run --model local:qwen3-vl-4b --mode Ju --sets E1,E1b,gen,web --workers 1
Writes <RUN_DIRS[set]>/<mode>__<name>/<image_id>.json (resumable), name = model without "local:"/"openai:".
API errors are not written (a rerun retries them); a local model's failure is written and scored as all wrong.
Seconds are wall time per request; with --workers > 1 they include queueing on a shared server, so latency is
measured on runs with --workers 1 (the report says which).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from e1.vlm import PROMPT, RUN_DIRS, SCHEMA, SET_DIRS, set_items

ROOT = Path(__file__).resolve().parent.parent
OCR_RUN = "T__pp-ocrv6-gpu"  # E1b PP-OCRv6 GPU runs: {"lines": [{"text", "box": [x0, y0, x1, y1]}]}

PROMPT_TEXT = """Dưới đây là chữ do OCR đọc từ ảnh chụp màn hình một đoạn chat tiếng Việt trên điện thoại (không có ảnh). \
Mỗi dòng có dạng [x=<trái>-<phải>] <chữ>, với vị trí ngang tính theo tỉ lệ bề rộng ảnh (0 = mép trái, 1 = mép phải), \
xếp từ trên xuống. Các dòng liền nhau có thể thuộc cùng một bong bóng chat. Bong bóng lệch trái là người kia gửi, lệch \
phải là chủ máy gửi. Dòng giờ, tên ứng dụng, thanh trạng thái không phải tin nhắn.
Trích xuất theo schema:
- messages: mọi bong bóng chat, từ trên xuống. side = "left" nếu bong bóng lệch trái, "right" nếu lệch phải. Bỏ giờ gửi.
- accounts, phones, links, amounts: mọi số tài khoản ngân hàng, số điện thoại, đường link/tên miền, số tiền xuất hiện \
trong các tin nhắn.

Quy tắc bắt buộc cho các chuỗi:
- Chép NGUYÊN VĂN từng ký tự như trong chữ OCR, giữ nguyên dấu cách, dấu chấm, chữ hoa/thường, tiền tố (https://, +84) và \
đơn vị tiền (đ, VND, k, tr). Link bị xuống dòng thì nối lại.
- KHÔNG sửa lỗi chính tả, KHÔNG đổi định dạng, KHÔNG đoán cho "hợp lý".
- Không có thì để mảng rỗng.
<ocr>
{ocr}
</ocr>"""


def ocr_lines(set_name: str, image_id: str) -> list[dict]:
    rec = json.loads((ROOT / RUN_DIRS[set_name] / OCR_RUN / f"{image_id}.json").read_text(encoding="utf-8"))
    return rec.get("lines", [])


def ocr_text(lines: list[dict], width: float) -> str:
    out = []
    for l in lines:
        x0, _, x1, _ = l["box"]
        out.append(f"[x={x0 / width:.2f}-{x1 / width:.2f}] {l['text']}")
    return "\n".join(out)


def run_name(model: str) -> str:
    return model.split(":", 1)[1] if ":" in model else model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--mode", choices=["J", "Ju", "O", "JO"], required=True)
    ap.add_argument("--sets", default="E1,E1b,gen,web")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cap-usd", type=float, default=3.0, help="stop when this invocation has spent this much")
    ap.add_argument("--max-tokens", type=int, default=4096)
    a = ap.parse_args()
    if a.mode == "Ju":
        os.environ["LOCAL_LLM_SCHEMA"] = "0"
    from core import llm
    local = a.model.startswith("local:")
    todo = []
    for s in a.sets.split(","):
        out = ROOT / RUN_DIRS[s] / f"{a.mode}__{run_name(a.model)}"
        out.mkdir(parents=True, exist_ok=True)
        for m in set_items(ROOT / SET_DIRS[s], s):
            if not (out / f"{m['image_id']}.json").exists():
                todo.append((s, m, out))
    print(f"{a.mode} {a.model}: {len(todo)} images to run, workers {a.workers}", flush=True)

    def work(s, m, out):
        if llm.USAGE.usd >= a.cap_usd:
            return None
        path = ROOT / SET_DIRS[s] / m["path"]
        rec = {"image_id": m["image_id"], "set": s, "config": f"{a.mode}__{run_name(a.model)}", "model": a.model,
               "workers": a.workers}
        try:
            if a.mode in ("O", "JO"):
                from PIL import Image  # only the OCR modes need the image width
                w = Image.open(path).size[0]
            if a.mode == "O":
                r = llm.generate(PROMPT_TEXT.format(ocr=ocr_text(ocr_lines(s, m["image_id"]), w)), schema=SCHEMA,
                                 model=a.model, retries=2, max_tokens=a.max_tokens)
            else:
                prompt = PROMPT
                if a.mode == "JO":
                    from e1.lora_train import user_text
                    prompt = user_text(ocr_lines(s, m["image_id"]), w)
                r = llm.generate(prompt, image=path.read_bytes(), schema=SCHEMA, model=a.model, retries=2,
                                 max_tokens=a.max_tokens)
            rec.update(output=r.output, seconds=r.seconds, tokens_in=r.tokens_in, tokens_out=r.tokens_out,
                       usd=r.usd, retries=r.retries)
            if s != "web":
                rec["raw"] = r.text[:6000]
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            if not local:
                return rec
        (out / f"{m['image_id']}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return rec

    t0, n, errors = time.time(), 0, 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(work, *x) for x in todo]
        for f in as_completed(futs):
            r = f.result()
            if r is None:
                continue
            n += 1
            if "error" in r:
                errors += 1
                print("ERR", r["set"], r["image_id"], r["error"][:160], flush=True)
            if n % 20 == 0:
                print(f"  {n}/{len(todo)} {time.time() - t0:.0f}s USD {llm.USAGE.usd:.3f}", flush=True)
    stopped = llm.USAGE.usd >= a.cap_usd
    print(json.dumps({"model": a.model, "mode": a.mode, "done": n, "errors": errors, "usd": round(llm.USAGE.usd, 4),
                      "cap_stop": stopped, "minutes": round((time.time() - t0) / 60, 1)}), flush=True)


if __name__ == "__main__":
    main()
