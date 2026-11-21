"""Generate the E1b hard set (100 images) + ground truth.

- nho33   : E1 orig downscaled to 33%                                   (30)
- nen2    : JPEG q30 -> resize 70% -> JPEG q30 (forwarded through apps)  (30)
- chuplai : photo of a screen: bezel + desk background, 2-4 deg rotation, mild perspective,
            light moire, blur, sensor noise, JPEG q85                     (30)
- dai     : long scrolling screenshot, 20-30 messages, width 390 @3x, targets spread
            over start / middle / end                                    (10)

Ground truth comes from E1's generator (data/E1/gt/<base>__orig.json) or from the render itself.
Also creates data/E1b/real/{images,gt}/ for the 'web' set (public real chat screenshots, collected by the planner tab).

Usage: python -m e1.gen_hard --e1 data/E1 --out data/E1b [--seed 20261121]
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from e1.gen_data import CSS, MEASURE_JS, SCALE, STYLES, W, base_gt, render_html
from e1.scenarios import DIALOGS, build

HARD_VARIANTS = ("nho33", "nen2", "chuplai", "dai")

# Short neutral chit-chat used to make long conversations; no digits, links or money.
FILLERS = {
    "left": ["Dạ vâng ạ", "Mình đang kiểm tra lại nhé", "Bạn đợi mình chút xíu", "Ok bạn",
             "Hôm nay bên mình đông quá", "Bạn còn ở đó không ạ?", "Mình gửi lại thông tin bên dưới",
             "Dạ đúng rồi ạ", "Bạn yên tâm nhé", "Không sao đâu ạ", "Mình hiểu rồi",
             "Bạn đọc kỹ giúp mình nhé", "Để mình hỏi lại quản lý", "Vâng, mình xin lỗi vì sự bất tiện",
             "Bạn làm theo hướng dẫn là được", "Cảm ơn bạn đã phản hồi"],
    "right": ["Ừ", "Ok", "Thật không vậy?", "Để mình xem", "Sao lâu thế", "Mình đang bận chút",
              "Gửi lại giúp mình với", "Mình chưa hiểu lắm", "Có chắc không bạn?", "Ừ được",
              "Đợi mình xíu nhé", "Mình hỏi người nhà đã", "Vậy à", "Rồi sao nữa?", "Hmm"],
}


def scale_gt(gt: dict, s: float) -> dict:
    for lst in gt["strings"].values():
        for e in lst:
            e["boxes"] = [[round(v * s, 1) for v in b] for b in e["boxes"]]
    for m in gt["messages"]:
        m["box"] = [round(v * s, 1) for v in m["box"]]
    return gt


def map_gt(gt: dict, fn) -> dict:
    """Map every box through a point function and keep the axis-aligned bounding box."""
    def mb(b):
        pts = [fn(x, y) for x, y in ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3]))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]
    for lst in gt["strings"].values():
        for e in lst:
            e["boxes"] = [mb(b) for b in e["boxes"]]
    for m in gt["messages"]:
        m["box"] = mb(m["box"])
    return gt


def jpeg(im: Image.Image, q: int) -> Image.Image:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def homography(src, dst):
    """3x3 H with dst ~ H @ src."""
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.asarray(A, float))
    H = vt[-1].reshape(3, 3)
    return H / H[2, 2]


def rephotograph(im: Image.Image, rng: random.Random):
    """Simulate a phone photo of another phone's screen. Returns (image, point map fn)."""
    nrng = np.random.default_rng(rng.randrange(2 ** 32))
    s = 0.62                                          # screen size in the photo relative to the screenshot
    sw, sh = im.width * s, im.height * s
    bez = 26 * s / 0.62                               # phone bezel width (px in the photo)
    cw, ch = int(sw + 2 * bez + 260), int(sh + 2 * bez + 300)
    cx, cy = cw / 2 + rng.uniform(-30, 30), ch / 2 + rng.uniform(-30, 30)
    ang = math.radians(rng.choice((-1, 1)) * rng.uniform(2, 4))

    def place(x, y, w, h):  # screen-space corner offsets -> rotated canvas coordinates
        dx, dy = x - w / 2, y - h / 2
        return (cx + dx * math.cos(ang) - dy * math.sin(ang), cy + dx * math.sin(ang) + dy * math.cos(ang))

    # Mild perspective: top edge slightly narrower or wider than the bottom, plus a small corner jitter
    k = rng.uniform(0.02, 0.045) * rng.choice((-1, 1))
    corners = [(-k * sw, 0), (sw + k * sw, 0), (sw - k * sw * 0.3, sh), (k * sw * 0.3, sh)]
    corners = [(x + rng.uniform(-6, 6), y + rng.uniform(-6, 6)) for x, y in corners]
    dst = [place(x, y, sw, sh) for x, y in corners]
    src = [(0, 0), (im.width, 0), (im.width, im.height), (0, im.height)]
    H = homography(src, dst)
    Hinv = np.linalg.inv(H)

    # Desk background: warm gradient + texture
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    base = np.array(rng.choice([(150, 120, 90), (120, 120, 125), (175, 160, 140), (70, 70, 75)]), np.float32)
    grad = 0.85 + 0.3 * (xx / cw) * (yy / ch)
    bg = base[None, None, :] * grad[..., None] + nrng.normal(0, 6, (ch, cw, 1))
    canvas = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    # Phone body (bezel) as a dark rounded quad around the screen
    body = [place(x, y, sw, sh) for x, y in ((-bez, -bez * 1.6), (sw + bez, -bez * 1.6), (sw + bez, sh + bez * 1.6),
                                              (-bez, sh + bez * 1.6))]
    ImageDraw.Draw(canvas).polygon(body, fill=(18, 18, 20))

    # Warp the screenshot into the canvas (inverse mapping for PIL)
    coeffs = (Hinv / Hinv[2, 2]).flatten()[:8]
    warped = im.convert("RGB").transform((cw, ch), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    mask = Image.new("L", im.size, 255).transform((cw, ch), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    canvas.paste(warped, (0, 0), mask)

    # Moire on the screen area, glare, blur, noise
    a = np.asarray(canvas).astype(np.float32)
    th = rng.uniform(0, math.pi)
    period = rng.uniform(5.0, 8.0)
    moire = 1 + 0.045 * np.sin(2 * math.pi * (xx * math.cos(th) + yy * math.sin(th)) / period)
    m = np.asarray(mask, np.float32)[..., None] / 255
    a = a * (1 - m) + a * m * moire[..., None]
    gx, gy = rng.uniform(0.2, 0.8) * cw, rng.uniform(0.1, 0.5) * ch
    glare = 22 * np.exp(-(((xx - gx) / (0.35 * cw)) ** 2 + ((yy - gy) / (0.25 * ch)) ** 2))
    a = a + glare[..., None] * m
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(rng.uniform(0.9, 1.3)))
    a = np.asarray(out).astype(np.float32) + nrng.normal(0, 5, (ch, cw, 3))
    out = jpeg(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), 85)

    def fn(x, y):
        p = H @ np.array([x, y, 1.0])
        return p[0] / p[2], p[1] / p[2]
    return out, fn


def long_conversation(rng: random.Random, scenario: int, n_total: int):
    """Full scenario dialog spread over n_total messages: target messages near the start, middle and end."""
    conv = build(rng, scenario, len(DIALOGS[scenario]))
    D = conv.messages
    tmask = [("[[" in t and any(f":{k}]]" in t for k in conv.targets)) for _, t in D]
    T = [i for i, m in enumerate(tmask) if m]
    first, last = T[0], T[-1]
    lo, hi = first + rng.randint(0, 1), n_total - 1 - (len(D) - 1 - last) - rng.randint(0, 1)
    anchors = [round(lo + (hi - lo) * j / (len(T) - 1)) for j in range(len(T))]
    pos = [0] * len(D)
    for j, i in enumerate(T):
        pos[i] = anchors[j]
    for i in range(first - 1, -1, -1):         # non-target lines before the first target: right before it
        pos[i] = pos[i + 1] - 1
    for a, b in zip(T, T[1:]):                  # between targets: right after the previous one
        for i in range(a + 1, b):
            pos[i] = pos[i - 1] + 1
    for i in range(last + 1, len(D)):           # after the last target
        pos[i] = pos[i - 1] + 1
    assert pos == sorted(set(pos)) and pos[0] >= 0 and pos[-1] < n_total, pos
    slots = [None] * n_total
    for i, p in enumerate(pos):
        slots[p] = D[i]
    prev = "right"
    for p in range(n_total):
        if slots[p] is None:
            side = "left" if prev == "right" or rng.random() < 0.4 else "right"
            slots[p] = (side, rng.choice(FILLERS[side]))
        prev = slots[p][0]
    conv.messages = slots
    return conv


def gen_long(out: Path, seed: int):
    from playwright.sync_api import sync_playwright
    rows = []
    long_css = CSS.replace("html, body { width: 390px; height: 844px; overflow: hidden; }",
                           "html, body { width: 390px; }").replace(
        ".phone { width: 390px; height: 844px;", ".phone { width: 390px;").replace(
        ".chat { flex: 1; overflow: hidden;", ".chat {")
    assert long_css.count("844") == 0
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": 844}, device_scale_factor=SCALE)
        for j in range(10):
            style, scenario = STYLES[j % 3], j % 5 + 1
            base_id = f"{style}_L{j:02d}"

            def render(attempt):
                rng = random.Random(f"{seed}-{base_id}-{attempt}")
                conv = long_conversation(rng, scenario, rng.randint(20, 30))
                doc = render_html(conv, style, False, random.Random(f"{seed}-{base_id}-time")).replace(CSS, long_css)
                page.set_content(doc)
                page.evaluate("document.fonts.ready")
                height = math.ceil(page.evaluate("document.querySelector('.phone').getBoundingClientRect().height"))
                page.set_viewport_size({"width": W, "height": height})
                meas = page.evaluate(MEASURE_JS)
                ok = all(t["lines"] == 1 and t["box"][2] <= t["bubbleRight"] - 6 for t in meas["targets"])
                return conv, doc, meas, height * SCALE, ok

            tried = []
            for attempt in range(40):
                conv, doc, meas, hpx, ok = render(attempt)
                if ok and 3000 <= hpx <= 5000:
                    break
                if ok:
                    tried.append((hpx, attempt))
            else:
                # long-worded scenarios cannot reach 20 messages under 5000 px: take the shortest one, up to 5600
                hpx, attempt = min(tried)
                if hpx > 5600:
                    raise RuntimeError(f"cannot fit {base_id}")
                conv, doc, meas, hpx, ok = render(attempt)
            img = Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")
            (out / "html" / f"{base_id}.html").write_text(doc, encoding="utf-8")
            gt = base_gt(conv, style, base_id, meas)
            gt["n_messages"] = len(conv.messages)
            rows.append((base_id, style, scenario, img, gt))
            print(base_id, "msgs", len(conv.messages), "size", img.size, flush=True)
        browser.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e1", default="data/E1")
    ap.add_argument("--out", default="data/E1b")
    ap.add_argument("--seed", type=int, default=20261121)
    args = ap.parse_args()
    e1, out = Path(args.e1), Path(args.out)
    for d in ("images", "gt", "html", "real/images", "real/gt"):
        (out / d).mkdir(parents=True, exist_ok=True)
    manifest = []

    def save(image_id, base_id, style, scenario, variant, im, ext, gt, **kw):
        path = out / "images" / f"{image_id}.{ext}"
        if ext == "jpg":
            im.save(path, quality=kw.get("q", 92))
        else:
            im.save(path, optimize=True)
        g = {**gt, "image_id": image_id, "variant": variant, "size": list(im.size)}
        (out / "gt" / f"{image_id}.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest.append({"image_id": image_id, "base_id": base_id, "style": style, "variant": variant,
                         "scenario": scenario, "path": f"images/{image_id}.{ext}"})

    bases = sorted({json.loads(l)["base_id"] for l in open(e1 / "manifest.jsonl", encoding="utf-8")})
    for base_id in bases:
        gt0 = json.loads((e1 / "gt" / f"{base_id}__orig.json").read_text(encoding="utf-8"))
        for k in ("image_id", "variant", "size"):
            gt0.pop(k, None)
        im = Image.open(e1 / "images" / f"{base_id}__orig.png").convert("RGB")
        style, scenario = gt0["style"], gt0["scenario"]
        rng = random.Random(f"{args.seed}-{base_id}")

        small = im.resize((round(im.width * 0.33), round(im.height * 0.33)), Image.LANCZOS)
        save(f"{base_id}__nho33", base_id, style, scenario, "nho33", small, "png",
             scale_gt(json.loads(json.dumps(gt0)), 0.33))

        n2 = jpeg(im, 30)
        n2 = n2.resize((round(im.width * 0.7), round(im.height * 0.7)), Image.LANCZOS)
        save(f"{base_id}__nen2", base_id, style, scenario, "nen2", n2, "jpg",
             scale_gt(json.loads(json.dumps(gt0)), 0.7), q=30)

        photo, fn = rephotograph(im, rng)
        save(f"{base_id}__chuplai", base_id, style, scenario, "chuplai", photo, "jpg",
             map_gt(json.loads(json.dumps(gt0)), fn), q=92)
        print(base_id, "ok", flush=True)

    for base_id, style, scenario, img, gt in gen_long(out, args.seed):
        save(f"{base_id}__dai", base_id, style, scenario, "dai", img, "png", gt)

    with open(out / "manifest.jsonl", "w", encoding="utf-8") as f:
        for m in manifest:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    readme = out / "real" / "README.md"
    if not readme.exists():
        readme.write_text(
            "Bộ `web`: ảnh chat thật đã đăng công khai, do tab kế hoạch thu; nguồn từng ảnh ghi ở `sources.md`.\n"
            "Chỉ dùng để chấm nội bộ: không commit, không đưa ảnh vào report.\n"
            "Mỗi ảnh `images/web_NN.<png|jpg|webp>` cần một file `gt/web_NN.json`: tối thiểu `image_id` và `strings`\n"
            "(account/phone/link/amount: danh sách {raw} hoặc chuỗi). `messages` để rỗng; thiếu `norm` thì code chấm\n"
            "tự tính. Kết quả model ghi ra `data/E1b/web_runs/`, không ghi vào thư mục này.\n", encoding="utf-8")
    print("images:", len(manifest))


if __name__ == "__main__":
    main()
