"""Generate the E1 synthetic chat screenshots + ground truth.

30 base conversations (3 UI styles x 10), rendered with Playwright at 390x844 @3x,
then 6 variants each: orig, dark, crop, jpeg40, half, blur  -> 180 images.

Usage: python -m e1.gen_data --out data/E1 [--seed 20261120]
"""
from __future__ import annotations

import argparse
import html
import json
import random
from pathlib import Path

from PIL import Image, ImageFilter

from e1.scenarios import SCENARIOS, Conversation, build, plain_text, segments

W, H, SCALE = 390, 844, 3
STYLES = ("zalo", "messenger", "sms")
VARIANTS = ("orig", "dark", "crop", "jpeg40", "half", "blur")

CSS = r"""
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 390px; height: 844px; overflow: hidden; }
body { font-family: var(--font); -webkit-font-smoothing: antialiased; background: var(--bg); color: var(--fg); }
.phone { width: 390px; height: 844px; display: flex; flex-direction: column; }
.status { height: 44px; display: flex; align-items: center; justify-content: space-between; padding: 0 26px;
  font-size: 15px; font-weight: 600; background: var(--hdr-bg); color: var(--hdr-fg); }
.status .icons { display: flex; gap: 5px; align-items: center; }
.bar { width: 3px; background: currentColor; border-radius: 1px; display: inline-block; }
.batt { width: 24px; height: 11px; border: 1.5px solid currentColor; border-radius: 3px; position: relative; }
.batt::after { content: ""; position: absolute; left: 1.5px; top: 1.5px; bottom: 1.5px; width: 60%; background: currentColor; border-radius: 1px; }
.header { height: 56px; display: flex; align-items: center; gap: 10px; padding: 0 12px; background: var(--hdr-bg);
  color: var(--hdr-fg); border-bottom: 1px solid var(--hdr-border); }
.back { font-size: 30px; line-height: 1; width: 18px; color: var(--accent-hdr); }
.av { width: 36px; height: 36px; border-radius: 50%; background: var(--av); color: #fff; display: flex;
  align-items: center; justify-content: center; font-weight: 700; font-size: 14px; flex: none; }
.who { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.who b { font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.who small { font-size: 12px; opacity: .75; }
.chat { flex: 1; overflow: hidden; padding: 10px 10px 0; display: flex; flex-direction: column; gap: var(--gap); background: var(--chat-bg); }
.chip { align-self: center; font-size: 12px; color: var(--muted); background: var(--chip-bg); padding: 3px 10px; border-radius: 10px; margin: 4px 0; }
.row { display: flex; align-items: flex-end; gap: 6px; }
.row.right { justify-content: flex-end; }
.row .mini { width: 28px; height: 28px; border-radius: 50%; background: var(--av); flex: none; visibility: var(--mini-vis); }
.row.right .mini { display: none; }
.bubble { max-width: 74%; padding: 8px 12px; border-radius: var(--radius); font-size: 15.5px; line-height: 1.38;
  overflow-wrap: anywhere; }
.left .bubble { background: var(--l-bg); color: var(--l-fg); border: var(--l-border); }
.right .bubble { background: var(--r-bg); color: var(--r-fg); border: var(--r-border); }
.t { white-space: nowrap; }
.time { font-size: 11px; color: var(--muted); margin-top: 3px; display: var(--time-disp); }
.right .time { color: var(--r-time); }
.input { height: 64px; display: flex; align-items: center; gap: 10px; padding: 0 14px 10px; background: var(--hdr-bg);
  border-top: 1px solid var(--hdr-border); }
.input .field { flex: 1; height: 36px; border-radius: 18px; background: var(--field); color: var(--muted);
  display: flex; align-items: center; padding: 0 14px; font-size: 15px; }
.input .send { width: 30px; height: 30px; border-radius: 50%; background: var(--accent); }
"""

THEMES = {
    ("zalo", False): dict(font="'Noto Sans', Arial, sans-serif", bg="#fff", fg="#081c36", **{
        "hdr-bg": "#1b74e4", "hdr-fg": "#fff", "hdr-border": "#1b74e4", "accent-hdr": "#fff", "av": "#6aa4f0",
        "chat-bg": "#e2e9f1", "chip-bg": "rgba(0,0,0,.08)", "muted": "#7589a3", "gap": "8px", "radius": "10px",
        "l-bg": "#fff", "l-fg": "#081c36", "l-border": "none", "r-bg": "#dbebff", "r-fg": "#081c36",
        "r-border": "1px solid #c6dcf8", "r-time": "#7589a3", "time-disp": "block", "mini-vis": "visible",
        "field": "#eef0f2", "accent": "#1b74e4"}),
    ("zalo", True): dict(font="'Noto Sans', Arial, sans-serif", bg="#121212", fg="#e6e6e6", **{
        "hdr-bg": "#1f1f1f", "hdr-fg": "#e6e6e6", "hdr-border": "#2a2a2a", "accent-hdr": "#e6e6e6", "av": "#3b6fb6",
        "chat-bg": "#0e0e0e", "chip-bg": "rgba(255,255,255,.08)", "muted": "#8a8f98", "gap": "8px", "radius": "10px",
        "l-bg": "#2b2c2e", "l-fg": "#e6e6e6", "l-border": "none", "r-bg": "#16385f", "r-fg": "#e8f0fb",
        "r-border": "none", "r-time": "#8fa6c4", "time-disp": "block", "mini-vis": "visible",
        "field": "#2b2c2e", "accent": "#3b82f6"}),
    ("messenger", False): dict(font="Arial, 'Liberation Sans', sans-serif", bg="#fff", fg="#050505", **{
        "hdr-bg": "#fff", "hdr-fg": "#050505", "hdr-border": "#e4e6eb", "accent-hdr": "#a033ff", "av": "#b06ab3",
        "chat-bg": "#fff", "chip-bg": "transparent", "muted": "#65676b", "gap": "6px", "radius": "18px",
        "l-bg": "#f0f0f0", "l-fg": "#050505", "l-border": "none", "r-bg": "linear-gradient(180deg,#a033ff,#3b5bfd)",
        "r-fg": "#fff", "r-border": "none", "r-time": "#ddd", "time-disp": "none", "mini-vis": "visible",
        "field": "#f0f2f5", "accent": "#a033ff"}),
    ("messenger", True): dict(font="Arial, 'Liberation Sans', sans-serif", bg="#000", fg="#e4e6eb", **{
        "hdr-bg": "#000", "hdr-fg": "#e4e6eb", "hdr-border": "#222", "accent-hdr": "#b56cff", "av": "#8e4f91",
        "chat-bg": "#000", "chip-bg": "transparent", "muted": "#a8abaf", "gap": "6px", "radius": "18px",
        "l-bg": "#303030", "l-fg": "#e4e6eb", "l-border": "none", "r-bg": "linear-gradient(180deg,#8a2be2,#3b5bfd)",
        "r-fg": "#fff", "r-border": "none", "r-time": "#ccc", "time-disp": "none", "mini-vis": "visible",
        "field": "#242526", "accent": "#a033ff"}),
    ("sms", False): dict(font="'Noto Sans', 'DejaVu Sans', sans-serif", bg="#fff", fg="#000", **{
        "hdr-bg": "#f6f6f6", "hdr-fg": "#000", "hdr-border": "#d8d8d8", "accent-hdr": "#0a7aff", "av": "#9aa0a6",
        "chat-bg": "#fff", "chip-bg": "transparent", "muted": "#8e8e93", "gap": "7px", "radius": "18px",
        "l-bg": "#e9e9eb", "l-fg": "#000", "l-border": "none", "r-bg": "#30c35a", "r-fg": "#fff", "r-border": "none",
        "r-time": "#eee", "time-disp": "none", "mini-vis": "hidden", "field": "#fff", "accent": "#30c35a"}),
    ("sms", True): dict(font="'Noto Sans', 'DejaVu Sans', sans-serif", bg="#000", fg="#fff", **{
        "hdr-bg": "#1c1c1e", "hdr-fg": "#fff", "hdr-border": "#2c2c2e", "accent-hdr": "#0a84ff", "av": "#636366",
        "chat-bg": "#000", "chip-bg": "transparent", "muted": "#8e8e93", "gap": "7px", "radius": "18px",
        "l-bg": "#262628", "l-fg": "#fff", "l-border": "none", "r-bg": "#2fb14f", "r-fg": "#fff", "r-border": "none",
        "r-time": "#ddd", "time-disp": "none", "mini-vis": "hidden", "field": "#1c1c1e", "accent": "#2fb14f"}),
}


def initials(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[0].isalpha()]
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()


def render_html(conv: Conversation, style: str, dark: bool, rng: random.Random) -> str:
    theme = THEMES[(style, dark)]
    vars_css = ";".join(f"--{k}:{v}" for k, v in theme.items())
    hh, mm = rng.randint(8, 21), rng.randint(0, 50)
    subtitle = {"zalo": "Vừa truy cập", "messenger": "Hoạt động 5 phút trước", "sms": "Tin nhắn SMS"}[style]
    rows = []
    for i, (side, tpl) in enumerate(conv.messages):
        parts = []
        for kind, val in segments(tpl, conv):
            if kind == "br":
                parts.append("<br>")
            elif kind == "target":
                parts.append(f'<span class="t" data-tid="{val.key}">{html.escape(val.raw)}</span>')
            else:
                parts.append(html.escape(val))
        t = f"{hh:02d}:{(mm + i) % 60:02d}"
        rows.append(f'<div class="row {side}"><div class="mini"></div><div class="bubble" data-msg="{i}">'
                    f'{"".join(parts)}<div class="time">{t}</div></div></div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body style="{vars_css}"><div class="phone">
<div class="status"><span>{hh:02d}:{(mm + 7) % 60:02d}</span><span class="icons">
<span class="bar" style="height:5px"></span><span class="bar" style="height:7px"></span>
<span class="bar" style="height:9px"></span><span class="bar" style="height:11px"></span>
<span class="batt"></span></span></div>
<div class="header"><span class="back">&#8249;</span><div class="av">{initials(conv.contact)}</div>
<div class="who"><b>{html.escape(conv.contact)}</b><small>{subtitle}</small></div></div>
<div class="chat"><div class="chip">Hôm nay {hh:02d}:{mm:02d}</div>{"".join(rows)}</div>
<div class="input"><div class="field">Nhập tin nhắn</div><div class="send"></div></div>
</div></body></html>"""


MEASURE_JS = """() => {
  const r = e => { const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
  return {
    msgs: [...document.querySelectorAll('[data-msg]')].map(e => ({i: +e.dataset.msg, box: r(e)})),
    targets: [...document.querySelectorAll('[data-tid]')].map(e => ({key: e.dataset.tid, box: r(e),
      lines: e.getClientRects().length, bubbleRight: e.closest('.bubble').getBoundingClientRect().right})),
    chat: r(document.querySelector('.chat')),
  };
}"""


def scale_box(b, s=SCALE):
    return [round(v * s, 1) for v in b]


def base_gt(conv: Conversation, style: str, base_id: str, meas: dict) -> dict:
    tboxes = {t["key"]: t for t in meas["targets"]}
    strings = {k: [] for k in ("account", "phone", "link", "amount")}
    seen = set()
    for tgt in conv.targets.values():
        if tgt.key not in tboxes:
            continue
        m = tboxes[tgt.key]
        assert m["lines"] == 1, (base_id, tgt.raw)
        entry = {"raw": tgt.raw, "norm": tgt.norm, "box": scale_box(m["box"]), **tgt.extra}
        if (tgt.type, tgt.norm) not in seen:
            seen.add((tgt.type, tgt.norm))
            strings[tgt.type].append(entry)
    # A target may appear twice (same key) - keep every occurrence box for crop decisions
    occ = {}
    for t in meas["targets"]:
        occ.setdefault(t["key"], []).append(scale_box(t["box"]))
    for typ in strings:
        for e in strings[typ]:
            key = next(k for k, t in conv.targets.items() if t.norm == e["norm"] and t.type == typ)
            e["boxes"] = occ[key]
            del e["box"]
    msgs = [{"order": m["i"], "side": conv.messages[m["i"]][0], "text": plain_text(conv.messages[m["i"]][1], conv),
             "box": scale_box(m["box"])} for m in meas["msgs"]]
    return {"base_id": base_id, "style": style, "scenario": conv.scenario, "scenario_name": SCENARIOS[conv.scenario],
            "contact": conv.contact, "strings": strings, "messages": msgs, "ignore": {"strings": [], "messages": []}}


def derive_gt(gt: dict, variant: str, image_id: str, size) -> dict:
    g = json.loads(json.dumps(gt))
    g["image_id"], g["variant"], g["size"] = image_id, variant, list(size)
    if variant == "half":
        for typ in g["strings"].values():
            for e in typ:
                e["boxes"] = [[v / 2 for v in b] for b in e["boxes"]]
        for m in g["messages"]:
            m["box"] = [v / 2 for v in m["box"]]
    if variant == "crop":
        cy = g["crop_y"] = g.pop("_crop_y")
        for typ, lst in g["strings"].items():
            keep = []
            for e in lst:
                e["boxes"] = [[b[0], b[1] - cy, b[2], b[3] - cy] for b in e["boxes"]]
                if any(b[1] >= 0 for b in e["boxes"]):
                    keep.append(e)  # at least one full occurrence still visible
                elif any(b[3] > 0 for b in e["boxes"]):
                    g["ignore"]["strings"].append({"type": typ, "norm": e["norm"], "raw": e["raw"]})
            g["strings"][typ] = keep
        msgs = []
        for m in g["messages"]:
            m["box"] = [m["box"][0], m["box"][1] - cy, m["box"][2], m["box"][3] - cy]
            if m["box"][1] >= 0:
                msgs.append(m)
            elif m["box"][3] > 0:
                g["ignore"]["messages"].append(m)
        g["messages"] = msgs
    g.pop("_crop_y", None)
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/E1")
    ap.add_argument("--seed", type=int, default=20261120)
    args = ap.parse_args()
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "gt").mkdir(parents=True, exist_ok=True)
    (out / "html").mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    manifest = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=SCALE)
        for style in STYLES:
            for idx in range(10):
                scenario = idx // 2 + 1
                base_id = f"{style}_{idx:02d}"
                n_msgs = random.Random(f"{args.seed}-{base_id}-n").randint(4, 8)
                n_cur = n_msgs
                for attempt in range(20):
                    rng = random.Random(f"{args.seed}-{base_id}-{attempt}")
                    conv = build(rng, scenario, n_cur)
                    renders = {}
                    ok = True
                    for dark in (False, True):
                        trng = random.Random(f"{args.seed}-{base_id}-time")
                        doc = render_html(conv, style, dark, trng)
                        page.set_content(doc)
                        page.evaluate("document.fonts.ready")
                        meas = page.evaluate(MEASURE_JS)
                        last = max(m["box"][3] for m in meas["msgs"])
                        if last > meas["chat"][3] - 4:
                            n_cur -= 1  # too many messages for one screen
                            ok = False
                            break
                        # every target string must sit on one line, fully inside its bubble (no clipped text)
                        if any(t["lines"] != 1 or t["box"][2] > t["bubbleRight"] - 6 for t in meas["targets"]):
                            ok = False
                            break
                        renders[dark] = (doc, page.screenshot(), meas)
                    if ok:
                        break
                else:
                    raise RuntimeError(f"cannot fit {base_id}")
                (out / "html" / f"{base_id}.html").write_text(renders[False][0], encoding="utf-8")
                gt = base_gt(conv, style, base_id, renders[False][2])
                m0 = gt["messages"][0]["box"]
                gt["_crop_y"] = round(m0[1] + 0.5 * (m0[3] - m0[1]))

                import io
                light = Image.open(io.BytesIO(renders[False][1])).convert("RGB")
                dark_img = Image.open(io.BytesIO(renders[True][1])).convert("RGB")
                imgs = {
                    "orig": (light, "png"),
                    "dark": (dark_img, "png"),
                    "crop": (light.crop((0, gt["_crop_y"], light.width, light.height)), "png"),
                    "jpeg40": (light, "jpg"),
                    "half": (light.resize((light.width // 2, light.height // 2), Image.LANCZOS), "png"),
                    "blur": (light.filter(ImageFilter.GaussianBlur(radius=2.0)), "png"),
                }
                for variant in VARIANTS:
                    im, ext = imgs[variant]
                    image_id = f"{base_id}__{variant}"
                    path = out / "images" / f"{image_id}.{ext}"
                    if ext == "jpg":
                        im.save(path, quality=40)
                    else:
                        im.save(path, optimize=True)
                    g = derive_gt(gt, variant, image_id, im.size)
                    (out / "gt" / f"{image_id}.json").write_text(json.dumps(g, ensure_ascii=False, indent=1),
                                                               encoding="utf-8")
                    manifest.append({"image_id": image_id, "base_id": base_id, "style": style, "variant": variant,
                                     "scenario": scenario, "path": f"images/{image_id}.{ext}"})
                print(base_id, "msgs", len(conv.messages), "targets", len(conv.targets), flush=True)
        browser.close()
    with open(out / "manifest.jsonl", "w", encoding="utf-8") as f:
        for m in manifest:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print("images:", len(manifest))


if __name__ == "__main__":
    main()
