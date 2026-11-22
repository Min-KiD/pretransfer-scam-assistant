"""E1b 'gen' set and E4 'gen_ref' set: chat images made by Gemini's image model (Nano Banana 2.1).

- gen_sua (20): an E1 original screenshot edited into a photo of a hand-held phone showing that chat.
- gen_moi (20): a new conversation (same scenario generator as E1) rendered from a text description.
- gen_ref (150, --ref): a new conversation rendered in the look of a real image from data/E1b/real/images
  (app, theme, screenshot vs phone photo, capture conditions) without its names, numbers or links.
  Eval and demo only, never training data. Output data/E1b/gen_ref/ (images, intended, manifest.jsonl with
  the reference id per image, calls.jsonl); its own cap.

The intended answers (<out>/intended/<id>.json) are NOT the ground truth: image models misspell digits.
gen: every image is checked by eye, the reviewed answers go to e1/gen_review.json and e1.gen_apply writes
data/E1b/gen/gt/ and manifest.jsonl. gen_ref: see E4 task, Phần 4 (gemini-4-carbon + PP-OCRv6 read-back).

Cost: priced from usage_metadata with the 2026-11-20 list price of gemini-nano-banana-2.1 (input 1.50,
text/thinking output 7.50, image output 30.00 USD per 1M tokens; a 2K image = 1680 tokens = 0.0504 USD).
The run stops before a call that could push the total over --cap-usd (default 5), retries included.

Usage: python -m e1.gen_nb --out data/E1b/gen [--only gen_sua_03]
       python -m e1.gen_nb --ref --cap-usd 10 [--limit 6]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from e1.scenarios import build, plain_text
from e1.vlm import load_key

MODEL = "gemini-nano-banana-2.1"
PRICE_IN, PRICE_TEXT_OUT, PRICE_IMG_OUT = 1.50e-6, 7.50e-6, 30.0e-6
WORST_CALL_USD = 0.10  # 2K image + input image + thinking (observed 0.064-0.074), for the pre-call cap check
APP = {"zalo": "Zalo (blue header, white and light-blue bubbles)",
       "messenger": "Facebook Messenger (white background, grey bubbles on the left, purple-blue bubbles on the right)",
       "sms": "the default Android SMS app (grey bubbles on the left, green bubbles on the right)"}

PROMPT_SUA = (
    "Edit this image: turn this phone screenshot into a realistic photo, taken with another phone, of a smartphone "
    "held in one hand that displays exactly this chat on its screen. The phone is slightly tilted, with natural "
    "shadows and a mild glare on the glass, ordinary indoor background. Keep every character of all on-screen text "
    "exactly as in the screenshot: the same Vietnamese words, digits, links and money amounts. Do not add, remove, "
    "translate or change any text.")


def _lines(conv) -> str:
    return "\n".join(f'{i + 1}. [{side}] {plain_text(t, conv).replace(chr(10), " / ")}'
                     for i, (side, t) in enumerate(conv.messages))


def prompt_moi(conv, style: str) -> str:
    lines = [f'{i + 1}. [{side}] {plain_text(t, conv).replace(chr(10), " / ")}' for i, (side, t) in enumerate(conv.messages)]
    return (
        f"Create a realistic smartphone screenshot (portrait) of a Vietnamese chat conversation in an app that looks "
        f"like {APP[style]}. The header shows the contact name \"{conv.contact}\". Show exactly these messages from top "
        "to bottom, each in its own chat bubble; [left] bubbles are from the contact, [right] bubbles are from the "
        "phone owner. A \" / \" inside a message means a line break in that bubble.\n" + "\n".join(lines) +
        "\nRender every message text exactly as written, character for character, including every digit, link and "
        "money amount, with correct Vietnamese diacritics. Add only small timestamps and the usual app chrome; no "
        "other text.")


REF_APP = {"zalo": "Zalo", "messenger": "Facebook Messenger", "telegram": "Telegram",
           "sms": "the phone's SMS app (iOS Messages or Android Messages, whichever the reference shows)"}
REF_CAPTURE = {True: "The reference is a photo of a phone screen taken with another camera: make a photo too, showing "
                     "the phone screen at a slight angle with its edge visible, natural light, some glare and slight "
                     "softness, but every message still readable.",
               False: "The reference is a screenshot: make a plain, straight phone screenshot."}
PHOTO_NOTE = re.compile(r"photo of an? (phone|iphone)|photographed|phone photos", re.I)

PROMPT_REF = (
    "The image above is a reference: a real picture of a Vietnamese chat, published in the news. Create a NEW image "
    "of a {app} chat that looks as if it came from the same app and the same kind of capture as the reference: same "
    "app look (header, bubble shapes and colours) and the same light or dark theme. {capture} Show ONE phone screen "
    "with ONE chat, even if the reference is a collage. Do not reproduce anything a news publisher added: no red X, "
    "arrows, boxes, blurred or pixelated areas, watermarks, logos or captions. Do not copy any name, number, link, "
    "amount or sentence from the reference.\n"
    "The chat header shows the contact name \"{contact}\". Show exactly these messages from top to bottom, each in "
    "its own chat bubble; [left] bubbles are from the contact, [right] bubbles are from the phone owner. A \" / \" "
    "inside a message means a line break in that bubble.\n{lines}\n"
    "Render every message text exactly as written, character for character, including every digit, link and money "
    "amount, with correct Vietnamese diacritics, sharp enough to read. Add only small timestamps and the usual app "
    "chrome; no other text.")


def jobs_ref(real: Path, seed: int, n: int):
    """n images, references taken round-robin over a seeded shuffle of the real images, scenarios 1-5 in turn."""
    refs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((real / "gt").glob("*.json"))]
    refs = [r for r in refs if any((real / "images").glob(f"{r['image_id']}.*"))]
    random.Random(f"{seed}-gen_ref").shuffle(refs)
    out = []
    for i in range(n):
        r = refs[i % len(refs)]
        scenario = i % 5 + 1
        rng = random.Random(f"{seed}-gen_ref-{i}")
        conv = build(rng, scenario, rng.randint(5, 8))
        iid = f"gen_ref_{i:03d}"
        photo = bool(PHOTO_NOTE.search(r.get("notes") or ""))
        it = intended(conv, iid, "gen_ref", iid, r.get("app") or "", scenario)
        it["ref"], it["photo"] = r["image_id"], photo
        prompt = PROMPT_REF.format(app=REF_APP.get(r.get("app"), "chat app"), capture=REF_CAPTURE[photo],
                                   contact=conv.contact, lines=_lines(conv))
        out.append({"id": iid, "variant": "gen_ref", "prompt": prompt,
                    "image": next((real / "images").glob(f"{r['image_id']}.*")), "aspect": "3:4" if photo else "9:16",
                    "intended": it})
    return out


def intended(conv_or_gt, image_id, variant, base_id, style, scenario):
    if isinstance(conv_or_gt, dict):  # from an E1 gt file
        strings = {t: [{"raw": e["raw"], "norm": e["norm"]} for e in lst] for t, lst in conv_or_gt["strings"].items()}
    else:
        strings = {t: [] for t in ("account", "phone", "link", "amount")}
        for tg in conv_or_gt.targets.values():
            strings[tg.type].append({"raw": tg.raw, "norm": tg.norm})
    return {"image_id": image_id, "base_id": base_id, "style": style, "scenario": scenario, "variant": variant,
            "strings": strings, "messages": [], "ignore": {"strings": [], "messages": []}}


def jobs(e1: Path, seed: int):
    out = []
    bases = sorted({json.loads(l)["base_id"] for l in open(e1 / "manifest.jsonl", encoding="utf-8")})
    for i, b in enumerate([b for k, b in enumerate(bases) if k % 3 != 2][:20]):
        gt = json.loads((e1 / "gt" / f"{b}__orig.json").read_text(encoding="utf-8"))
        iid = f"gen_sua_{i:02d}"
        out.append({"id": iid, "variant": "gen_sua", "prompt": PROMPT_SUA, "image": e1 / "images" / f"{b}__orig.png",
                    "aspect": "9:16", "intended": intended(gt, iid, "gen_sua", b, gt["style"], gt["scenario"])})
    styles = ("zalo", "messenger", "sms")
    for i in range(20):
        style, scenario = styles[i % 3], i % 5 + 1
        rng = random.Random(f"{seed}-gen_moi-{i}")
        conv = build(rng, scenario, rng.randint(5, 8))
        iid = f"gen_moi_{i:02d}"
        out.append({"id": iid, "variant": "gen_moi", "prompt": prompt_moi(conv, style), "image": None,
                    "aspect": "9:16", "intended": intended(conv, iid, "gen_moi", iid, style, scenario)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e1", default="data/E1")
    ap.add_argument("--out", default="data/E1b/gen")
    ap.add_argument("--seed", type=int, default=20261122)
    ap.add_argument("--cap-usd", type=float, default=5.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="", help="comma list of ids to (re)generate")
    ap.add_argument("--ref", action="store_true", help="make the E4 gen_ref set instead of gen")
    ap.add_argument("--real", default="data/E1b/real")
    ap.add_argument("--n", type=int, default=150, help="--ref: number of images")
    ap.add_argument("--limit", type=int, default=0, help="make at most this many missing images")
    args = ap.parse_args()
    if args.ref and args.out == "data/E1b/gen":
        args.out = "data/E1b/gen_ref"
    out = Path(args.out)
    for d in ("images", "intended"):
        (out / d).mkdir(parents=True, exist_ok=True)
    calls_path = out / "calls.jsonl"
    spent = sum(json.loads(l)["usd"] for l in open(calls_path, encoding="utf-8")) if calls_path.exists() else 0.0
    lock = threading.Lock()

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=load_key(Path(__file__).resolve().parent.parent))
    todo = jobs_ref(Path(args.real), args.seed, args.n) if args.ref else jobs(Path(args.e1), args.seed)
    every = todo
    only = set(filter(None, args.only.split(",")))
    if only:
        todo = [j for j in todo if j["id"] in only]
    else:
        todo = [j for j in todo if not any((out / "images").glob(f"{j['id']}.*"))]
    if args.limit:
        todo = todo[:args.limit]
    print(f"already spent {spent:.3f} USD; {len(todo)} images to make", flush=True)

    def one(j):
        nonlocal spent
        (out / "intended" / f"{j['id']}.json").write_text(json.dumps(j["intended"], ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
        contents = [j["prompt"]]
        if j["image"]:
            mime = "image/png" if Path(j["image"]).suffix.lower() == ".png" else "image/jpeg"
            contents = [types.Part.from_bytes(data=Path(j["image"]).read_bytes(), mime_type=mime), j["prompt"]]
        cfg = types.GenerateContentConfig(response_modalities=["IMAGE"],
                                          image_config=types.ImageConfig(aspect_ratio=j["aspect"], image_size="2K"))
        err = "not run"
        for attempt in range(3):
            with lock:
                if spent + WORST_CALL_USD > args.cap_usd:
                    return j["id"], f"stopped: cap {args.cap_usd} USD (spent {spent:.3f})"
            t0 = time.perf_counter()
            try:
                r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:200]}"
                time.sleep(5 * (attempt + 1))
                continue
            u = r.usage_metadata
            img_tok = sum(d.token_count or 0 for d in (u.candidates_tokens_details or []) if "IMAGE" in str(d.modality))
            txt_tok = (u.candidates_token_count or 0) - img_tok + (u.thoughts_token_count or 0)
            usd = (u.prompt_token_count or 0) * PRICE_IN + img_tok * PRICE_IMG_OUT + max(0, txt_tok) * PRICE_TEXT_OUT
            parts = [p for c in (r.candidates or []) for p in ((c.content.parts if c.content else None) or [])
                     if p.inline_data]
            finish = [str(c.finish_reason) for c in (r.candidates or [])]
            rec = {"id": j["id"], "attempt": attempt + 1, "seconds": round(time.perf_counter() - t0, 1),
                   "tokens_in": u.prompt_token_count, "tokens_img": img_tok, "tokens_text": txt_tok,
                   "usd": round(usd, 5), "got_image": bool(parts), "finish": finish, "model_version": r.model_version}
            with lock:
                spent += usd
                with open(calls_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")
            if parts:
                p = parts[0].inline_data
                ext = "jpg" if "jpeg" in (p.mime_type or "") else "png"
                (out / "images" / f"{j['id']}.{ext}").write_bytes(p.data)
                return j["id"], f"ok {usd:.4f} USD"
            err = "no image in response"
        return j["id"], f"failed: {err}"

    with ThreadPoolExecutor(args.workers) as ex:
        for iid, msg in ex.map(one, todo):
            print(iid, msg, flush=True)
    print(f"total spent {spent:.3f} USD")
    if args.ref:  # manifest of the images that exist, with the reference each came from
        with open(out / "manifest.jsonl", "w", encoding="utf-8") as f:
            for j in every:
                img = next((out / "images").glob(f"{j['id']}.*"), None)
                if img:
                    it = j["intended"]
                    f.write(json.dumps({"image_id": j["id"], "base_id": j["id"], "style": it["style"],
                                        "variant": "gen_ref", "scenario": it["scenario"], "ref": it["ref"],
                                        "path": f"images/{img.name}"}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
