"""T6 part D: 5-image trial of `gpt-image-2.6-sunburst` on the E1b `gen_moi` recipe -> data/E1b/gen_gpt/.

Same conversations, prompts and intended files as data/E1b/gen/gen_moi_00..04 (e1.gen_nb.jobs, seed 20261122), so
each image can be set beside the Gemini (Nano Banana 2.1) image of the same id. The intended answers are not the
ground truth (image models misspell digits): the sonnet tab reads the images against them before any larger batch.

Image API `POST /v1/images/generations`, size 1024x1536 (the recommended portrait size; Gemini made 2K at 9:16),
quality `high`, complexity left at its default (`high`), PNG. Cost from the response's `usage` at the list prices of
the model page (read 2026-11-26): text input 5, image input 8, image output 30 USD per 1M tokens. The run stops
before a call that could push the total over --cap-usd.

  python -m e1.gen_gpt [--cap-usd 0.5] [--n 5]
"""
from __future__ import annotations

import argparse
import base64
import json
import time

import httpx

from core.llm import env_value
from core.scenarios import ROOT
from e1.gen_nb import jobs

MODEL = "gpt-image-2.6-sunburst"
SIZE, QUALITY = "1024x1536", "high"
PRICE_TEXT_IN, PRICE_IMG_IN, PRICE_IMG_OUT = 5e-6, 8e-6, 30e-6
WORST_CALL_USD = 0.10  # about 1,400 output tokens (0.042 USD) expected at this size and quality; margin for retries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/E1b/gen_gpt")
    ap.add_argument("--cap-usd", type=float, default=0.5)
    ap.add_argument("--n", type=int, default=5, help="the first N gen_moi conversations")
    a = ap.parse_args()
    out = ROOT / a.out
    for d in ("images", "intended"):
        (out / d).mkdir(parents=True, exist_ok=True)
    calls = out / "calls.jsonl"
    spent = sum(json.loads(l)["usd"] for l in open(calls, encoding="utf-8")) if calls.exists() else 0.0
    key = env_value("OPENAI_API_KEY")
    assert key, "OPENAI_API_KEY missing"
    todo = [j for j in jobs(ROOT / "data/E1", 20261122) if j["variant"] == "gen_moi"][: a.n]
    todo = [j for j in todo if not (out / "images" / f"{j['id']}.png").exists()]
    print(f"already spent {spent:.4f} USD; {len(todo)} images to make", flush=True)
    with httpx.Client(timeout=300) as http:
        for j in todo:
            (out / "intended" / f"{j['id']}.json").write_text(json.dumps(j["intended"], ensure_ascii=False, indent=1),
                                                              encoding="utf-8")
            for attempt in range(1, 4):
                if spent + WORST_CALL_USD > a.cap_usd:
                    print(f"STOPPED: cap {a.cap_usd} USD (spent {spent:.4f})", flush=True)
                    return
                t0 = time.perf_counter()
                r = http.post("https://api.openai.com/v1/images/generations",
                              headers={"Authorization": f"Bearer {key}"},
                              json={"model": MODEL, "prompt": j["prompt"], "size": SIZE, "quality": QUALITY,
                                    "output_format": "png", "n": 1})
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                u = body.get("usage") or {}
                det = u.get("input_tokens_details") or {}
                usd = (det.get("text_tokens", u.get("input_tokens", 0)) * PRICE_TEXT_IN
                       + det.get("image_tokens", 0) * PRICE_IMG_IN + u.get("output_tokens", 0) * PRICE_IMG_OUT)
                spent += usd
                data = (body.get("data") or [{}])[0].get("b64_json")
                rec = {"id": j["id"], "attempt": attempt, "status": r.status_code,
                       "seconds": round(time.perf_counter() - t0, 1), "usage": u, "usd": round(usd, 5),
                       "got_image": bool(data), "size": SIZE, "quality": QUALITY, "model": MODEL,
                       **({"error": str(body.get("error") or r.text)[:300]} if not data else {})}
                with open(calls, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if data:
                    (out / "images" / f"{j['id']}.png").write_bytes(base64.b64decode(data))
                    print(f"{j['id']} ok {usd:.4f} USD, {rec['seconds']} s, {u.get('output_tokens')} output tokens",
                          flush=True)
                    break
                print(f"{j['id']} attempt {attempt}: HTTP {r.status_code} {rec['error'][:200]}", flush=True)
                if r.status_code in (400, 401, 403):
                    return
                time.sleep(5 * attempt)
    print(f"total spent {spent:.4f} USD", flush=True)


if __name__ == "__main__":
    main()
