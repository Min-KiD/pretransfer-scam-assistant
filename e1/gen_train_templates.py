"""HTML/CSS chat-app look-alikes for the E4 training generator (e1/gen_train.py).

Eight templates, each light and dark: zalo, messenger, imessage, android (Google Messages), telegram, viber,
web (Zalo-PC-like desktop app) and whatsapp (held out: only in val_la). Everything is drawn with HTML/CSS/inline
SVG; no real logos, photos, names or numbers.

`page_html(spec, items, screen)` returns one screen. DOM contract read by gen_train.MEASURE_JS:
  .chat                      the scrolling message area (its rect is the visible region)
  [data-item=i]              every chat item (row, chip, card); i = index in spec["items"]
  [data-msg=i] > .txt        text bubbles; .txt holds exactly the message text (timestamp lives in .meta)
  [data-sid=k]               a generated string (answer or distractor), textContent == its raw text
  [data-bank] [data-holder]  bank / holder text that belongs to the account in the same item
  .bubble, .card             containers a string must stay inside (no clipped text)
"""
from __future__ import annotations

import html

TEMPLATES = ("zalo", "messenger", "imessage", "android", "telegram", "viber", "web", "whatsapp")
PHONE_SIZES = [(360, 780), (375, 812), (390, 844), (393, 852), (412, 915), (430, 932), (360, 740), (384, 854)]
DESKTOP_SIZES = [(1280, 800), (1366, 768), (1440, 900), (1536, 864)]

ICON = {  # 24x24 stroke icons
    "back": '<path d="M15 5l-7 7 7 7"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2"/>',
    "video": '<rect x="3" y="6" width="12" height="12" rx="2"/><path d="M15 10l6-3v10l-6-3z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M16 16l4 4"/>',
    "dots": '<circle cx="12" cy="5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="19" r="1.2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "cam": '<rect x="3" y="7" width="18" height="13" rx="2"/><circle cx="12" cy="13.5" r="3.5"/><path d="M8 7l2-3h4l2 3"/>',
    "img": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-6-6-9 9"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>',
    "smile": '<circle cx="12" cy="12" r="9"/><path d="M8 14a5 5 0 008 0M9 9.5v.5M15 9.5v.5"/>',
    "send": '<path d="M4 12l16-8-6 16-2-6z"/>',
    "like": '<path d="M7 11v9H4v-9zM7 11l4-7a2 2 0 012 2v4h5a2 2 0 012 2l-2 7a2 2 0 01-2 1H7"/>',
    "clip": '<path d="M16 7l-7 7a2 2 0 003 3l7-7a4 4 0 00-6-6l-7 7a6 6 0 008 8l6-6"/>',
    "call_missed": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2"/>'
                   '<path d="M15 3l6 6M21 3l-6 6"/>',
}


def icon(name: str, size: int = 22, color: str = "currentColor", width: float = 1.9) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{ICON[name]}</svg>')


BASE_CSS = r"""
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: var(--W); }
body { font-family: var(--font); -webkit-font-smoothing: antialiased; background: var(--chat-bg); color: var(--fg); }
.screen { width: var(--W); height: var(--H); display: flex; flex-direction: column; overflow: hidden; position: relative; }
.long .screen { height: auto; }
.status { height: 38px; flex: none; display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; font-size: 14.5px; font-weight: 600; background: var(--sb-bg); color: var(--sb-fg); }
.status .ic { display: flex; gap: 4px; align-items: center; }
.bar { width: 3px; background: currentColor; border-radius: 1px; display: inline-block; }
.batt { width: 23px; height: 11px; border: 1.5px solid currentColor; border-radius: 3px; position: relative; margin-left: 3px; }
.batt::after { content: ""; position: absolute; left: 1.5px; top: 1.5px; bottom: 1.5px; width: var(--batt, 60%);
  background: currentColor; border-radius: 1px; }
.header { flex: none; display: flex; align-items: center; gap: 10px; padding: 0 10px; height: 58px;
  background: var(--hdr-bg); color: var(--hdr-fg); border-bottom: 1px solid var(--hdr-border); }
.header .who { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.header .who b { font-size: 16.5px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.header .who small { font-size: 12.5px; opacity: .75; white-space: nowrap; }
.header .icons { display: flex; gap: 16px; color: var(--hdr-icon); }
.hav { width: 38px; height: 38px; border-radius: 50%; flex: none; color: #fff; display: flex; align-items: center;
  justify-content: center; font-weight: 700; font-size: 15px; background: var(--av); position: relative; }
.hav.on::after { content: ""; position: absolute; right: -1px; bottom: -1px; width: 11px; height: 11px; border-radius: 50%;
  background: #31a24c; border: 2px solid var(--hdr-bg); }
.chat { flex: 1; overflow: hidden; position: relative; background: var(--chat-bg); }
.long .chat { overflow: visible; flex: none; }
.inner { display: flex; flex-direction: column; gap: var(--gap); padding: 10px var(--side-pad, 10px) 14px; }
.chip { align-self: center; font-size: 12px; color: var(--muted); background: var(--chip-bg); padding: 3px 10px;
  border-radius: 10px; margin: 6px 0 2px; text-align: center; }
.row { display: flex; align-items: flex-end; gap: 7px; }
.row.right { justify-content: flex-end; }
.av { width: 28px; height: 28px; border-radius: 50%; flex: none; background: var(--av); color: #fff; font-size: 11px;
  font-weight: 700; display: var(--av-disp, flex); align-items: center; justify-content: center; }
.row.right .av { display: none; }
.row.cont .av { visibility: hidden; }
.bubble { max-width: var(--maxw, 76%); padding: var(--pad, 8px 12px); border-radius: var(--radius); font-size: var(--fs);
  line-height: 1.36; overflow-wrap: anywhere; position: relative; border: var(--b-border, none); }
.left .bubble { background: var(--l-bg); color: var(--l-fg); }
.right .bubble { background: var(--r-bg); color: var(--r-fg); border: var(--rb-border, var(--b-border, none)); }
.txt { white-space: pre-wrap; }
.s { white-space: nowrap; }
.s.link { white-space: normal; word-break: break-all; color: var(--link); text-decoration: var(--link-dec, none); }
.right .s.link { color: var(--r-link, var(--link)); }
.meta { font-size: 11px; color: var(--meta); white-space: nowrap; }
.right .meta { color: var(--r-meta, var(--meta)); }
.tm-below .meta { display: block; margin-top: 3px; }
.tm-inline .meta { float: right; margin: 7px -3px -4px 10px; font-size: 11px; }
.tm-none .meta { display: none; }
.react { position: absolute; right: -4px; bottom: -11px; font-size: 11px; background: var(--react-bg); border-radius: 9px;
  padding: 0 4px; box-shadow: 0 0 0 1.5px var(--chat-bg); }
.react + .meta { }
.card { border-radius: 14px; overflow: hidden; background: var(--card-bg); color: var(--card-fg);
  border: 1px solid var(--card-border); }
.media .pic { width: var(--pw); height: var(--ph); border-radius: 14px; }
.lcard { width: 236px; }
.lcard .th { height: 118px; }
.lcard .bd { padding: 8px 11px 10px; }
.lcard b { display: block; font-size: 13.5px; line-height: 1.3; }
.lcard small { display: block; font-size: 12px; color: var(--muted); margin-top: 3px; line-height: 1.3; }
.lcard i { display: block; font-style: normal; font-size: 11px; color: var(--muted); margin-top: 5px; text-transform: uppercase; }
.call { display: flex; align-items: center; gap: 10px; padding: 9px 14px 9px 10px; border-radius: 16px; }
.call .ci { width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  background: var(--call-bg); color: #e5484d; flex: none; }
.call b { display: block; font-size: 14px; }
.call small { display: block; font-size: 12px; color: var(--muted); }
.receipt { width: 258px; font-family: Arial, 'Liberation Sans', sans-serif; background: #fff; color: #1d2433; border: none; }
.receipt .top { padding: 12px 12px 10px; color: #fff; text-align: center; }
.receipt .top .ok { width: 34px; height: 34px; border-radius: 50%; background: rgba(255,255,255,.25); margin: 0 auto 6px;
  display: flex; align-items: center; justify-content: center; font-size: 19px; }
.receipt .top b { display: block; font-size: 14px; }
.receipt .amt { font-size: 21px; font-weight: 700; margin-top: 4px; white-space: nowrap; }
.receipt .rows { padding: 8px 12px 10px; }
.receipt .r { display: flex; justify-content: space-between; gap: 8px; font-size: 11.5px; padding: 4px 0;
  border-bottom: 1px dashed #dde2ea; }
.receipt .r:last-child { border-bottom: none; }
.receipt .r span:first-child { color: #6b7280; flex: none; }
.receipt .r span:last-child { text-align: right; font-weight: 600; overflow-wrap: anywhere; }
.input { flex: none; display: flex; align-items: center; gap: 12px; padding: 8px 12px 12px; background: var(--in-bg);
  color: var(--in-icon); border-top: 1px solid var(--hdr-border); }
.input .field { flex: 1; height: 38px; border-radius: 19px; background: var(--field); color: var(--muted); display: flex;
  align-items: center; padding: 0 14px; font-size: 15px; white-space: nowrap; overflow: hidden; }
.nav { flex: none; height: 30px; display: flex; align-items: center; justify-content: center; background: var(--in-bg); }
.nav .gl { width: 120px; height: 4.5px; border-radius: 3px; background: var(--fg); opacity: .8; }
.nav3 { justify-content: space-around; color: var(--fg); opacity: .7; font-size: 16px; }
"""

# Per-template CSS on top of BASE_CSS; colours as variables per light/dark.
TPL_CSS = {
    "zalo": r"""
.header { height: 56px; }
.header .who b { font-size: 16px; }
.bubble { box-shadow: 0 1px 1px rgba(0,0,0,.06); }
""",
    "messenger": r"""
.header { height: 60px; border-bottom: none; box-shadow: 0 1px 2px rgba(0,0,0,.08); }
.inner { gap: 3px; }
.row.gap { margin-top: 8px; }
.chip { font-weight: 500; }
""",
    "imessage": r"""
.header { height: 92px; flex-direction: column; justify-content: center; gap: 3px; position: relative; padding-top: 4px; }
.header .back { position: absolute; left: 8px; top: 16px; color: var(--hdr-icon); display: flex; align-items: center; font-size: 17px; }
.header .vid { position: absolute; right: 14px; top: 18px; color: var(--hdr-icon); }
.header .hav { width: 50px; height: 50px; font-size: 19px; background: linear-gradient(#a5abb8,#858994); }
.header .nm { font-size: 12.5px; display: flex; align-items: center; gap: 2px; }
.inner { gap: 3px; }
.row.gap { margin-top: 9px; }
.chip { background: none; font-size: 11.5px; font-weight: 500; }
""",
    "android": r"""
.header { height: 64px; border-bottom: none; }
.header .who b { font-size: 19px; font-weight: 500; }
.inner { gap: 4px; }
.row.gap { margin-top: 10px; }
.chip { background: none; font-size: 12px; }
.tm-out { font-size: 11.5px; color: var(--meta); margin: 2px 6px 4px 42px; }
.right + .tm-out { align-self: flex-end; margin-right: 4px; }
""",
    "telegram": r"""
.header { height: 56px; }
.chat { background: var(--wall); }
.inner { gap: 4px; }
.row.gap { margin-top: 7px; }
.chip { background: var(--chip-bg); color: var(--chip-fg); font-weight: 600; }
.bubble { box-shadow: 0 1px 1px rgba(0,0,0,.12); }
""",
    "viber": r"""
.header { height: 58px; }
.inner { gap: 5px; }
.row.gap { margin-top: 9px; }
""",
    "whatsapp": r"""
.header { height: 60px; }
.chat { background: var(--wall); }
.inner { gap: 3px; }
.row.gap { margin-top: 9px; }
.chip { background: var(--chip-bg); color: var(--chip-fg); text-transform: uppercase; font-size: 11.5px; border-radius: 7px; }
.bubble { box-shadow: 0 1px .5px rgba(11,20,26,.13); }
""",
    "web": r"""
.screen { flex-direction: row; }
.rail { width: 64px; flex: none; background: var(--rail); display: flex; flex-direction: column; align-items: center;
  gap: 22px; padding-top: 18px; color: #fff; }
.rail .me { width: 44px; height: 44px; border-radius: 50%; background: #8fb5f8; border: 2px solid #fff; }
.side { width: 330px; flex: none; background: var(--side-bg); border-right: 1px solid var(--hdr-border); display: flex;
  flex-direction: column; }
.side .sr { height: 64px; display: flex; align-items: center; padding: 0 14px; gap: 10px; border-bottom: 1px solid var(--hdr-border); }
.side .sr .f { flex: 1; height: 34px; border-radius: 8px; background: var(--field); color: var(--muted); display: flex;
  align-items: center; padding: 0 10px; gap: 6px; font-size: 13.5px; }
.conv { display: flex; gap: 11px; padding: 11px 14px; align-items: center; }
.conv.act { background: var(--side-act); }
.conv .hav { width: 46px; height: 46px; }
.conv .cw { flex: 1; min-width: 0; }
.conv .cw b { display: block; font-size: 14.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv .cw small { display: block; font-size: 13px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 3px; }
.conv em { font-style: normal; font-size: 12px; color: var(--muted); align-self: flex-start; margin-top: 3px; }
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.header { height: 68px; padding: 0 18px; }
.header .hav { width: 46px; height: 46px; }
.inner { gap: 8px; padding: 14px 22px 16px; }
.bubble { box-shadow: 0 1px 1px rgba(0,0,0,.06); }
.input { padding: 10px 16px; }
.input .field { border-radius: 6px; }
""",
}

LIGHT, DARK = 0, 1
COMMON = {"font": "'Noto Sans', Arial, sans-serif"}
THEMES = {
    "zalo": (
        dict(**{"chat-bg": "#e2e9f1", "fg": "#081c36", "sb-bg": "#0068ff", "sb-fg": "#fff", "hdr-bg": "#0068ff",
                "hdr-fg": "#fff", "hdr-icon": "#fff", "hdr-border": "#0068ff", "av": "#6aa4f0", "l-bg": "#fff",
                "l-fg": "#081c36", "r-bg": "#e5efff", "r-fg": "#081c36", "rb-border": "1px solid #c7dbfa",
                "link": "#0068ff", "meta": "#7589a3", "muted": "#7589a3", "chip-bg": "rgba(0,0,0,.12)",
                "radius": "10px", "gap": "9px", "fs": "15px", "in-bg": "#fff", "in-icon": "#7589a3", "field": "#fff",
                "card-bg": "#fff", "card-fg": "#081c36", "card-border": "transparent", "call-bg": "#fdecec",
                "react-bg": "#fff"}),
        dict(**{"chat-bg": "#0d0d0d", "fg": "#e8eaed", "sb-bg": "#1f1f1f", "sb-fg": "#e8eaed", "hdr-bg": "#1f1f1f",
                "hdr-fg": "#e8eaed", "hdr-icon": "#c9ccd1", "hdr-border": "#2a2a2a", "av": "#3b6fb6", "l-bg": "#2a2b2d",
                "l-fg": "#e8eaed", "r-bg": "#1c3b66", "r-fg": "#e8f0fb", "rb-border": "none", "link": "#5aa2ff",
                "meta": "#8a8f98", "muted": "#8a8f98", "chip-bg": "rgba(255,255,255,.1)", "radius": "10px",
                "gap": "9px", "fs": "15px", "in-bg": "#1f1f1f", "in-icon": "#9aa0a6", "field": "#1f1f1f",
                "card-bg": "#2a2b2d", "card-fg": "#e8eaed", "card-border": "transparent", "call-bg": "#3a2326",
                "react-bg": "#2a2b2d"})),
    "messenger": (
        dict(**{"chat-bg": "#fff", "fg": "#050505", "sb-bg": "#fff", "sb-fg": "#050505", "hdr-bg": "#fff",
                "hdr-fg": "#050505", "hdr-icon": "#8a3ffc", "hdr-border": "#e4e6eb", "av": "#b06ab3", "l-bg": "#f0f0f0",
                "l-fg": "#050505", "r-bg": "#0084ff", "r-fg": "#fff", "link": "#050505", "r-link": "#fff",
                "link-dec": "underline", "meta": "#65676b", "muted": "#65676b", "chip-bg": "transparent",
                "radius": "18px", "gap": "3px", "fs": "15.5px", "in-bg": "#fff", "in-icon": "#8a3ffc",
                "field": "#f0f2f5", "card-bg": "#f0f0f0", "card-fg": "#050505", "card-border": "transparent",
                "call-bg": "#e4e6eb", "react-bg": "#fff", "av-disp": "flex"}),
        dict(**{"chat-bg": "#000", "fg": "#e4e6eb", "sb-bg": "#000", "sb-fg": "#e4e6eb", "hdr-bg": "#000",
                "hdr-fg": "#e4e6eb", "hdr-icon": "#b56cff", "hdr-border": "#222", "av": "#8e4f91", "l-bg": "#303030",
                "l-fg": "#e4e6eb", "r-bg": "linear-gradient(180deg,#a033ff,#5b4dfd)", "r-fg": "#fff", "link": "#e4e6eb",
                "r-link": "#fff", "link-dec": "underline", "meta": "#a8abaf", "muted": "#a8abaf",
                "chip-bg": "transparent", "radius": "18px", "gap": "3px", "fs": "15.5px", "in-bg": "#000",
                "in-icon": "#b56cff", "field": "#242526", "card-bg": "#303030", "card-fg": "#e4e6eb",
                "card-border": "transparent", "call-bg": "#3a3b3c", "react-bg": "#303030"})),
    "imessage": (
        dict(**{"chat-bg": "#fff", "fg": "#000", "sb-bg": "#f6f6f6", "sb-fg": "#000", "hdr-bg": "#f6f6f6",
                "hdr-fg": "#000", "hdr-icon": "#0a7aff", "hdr-border": "#d8d8d8", "av": "#9aa0a6", "l-bg": "#e9e9eb",
                "l-fg": "#000", "r-bg": "var(--ios-r, #0b84fe)", "r-fg": "#fff", "link": "#0a60d0", "r-link": "#fff",
                "link-dec": "underline", "meta": "#8e8e93", "muted": "#8e8e93", "chip-bg": "transparent",
                "radius": "18px", "gap": "3px", "fs": "16px", "in-bg": "#fff", "in-icon": "#8e8e93", "field": "#fff",
                "card-bg": "#e9e9eb", "card-fg": "#000", "card-border": "transparent", "call-bg": "#fff",
                "react-bg": "#e9e9eb", "av-disp": "none"}),
        dict(**{"chat-bg": "#000", "fg": "#fff", "sb-bg": "#1c1c1e", "sb-fg": "#fff", "hdr-bg": "#1c1c1e",
                "hdr-fg": "#fff", "hdr-icon": "#0a84ff", "hdr-border": "#2c2c2e", "av": "#636366", "l-bg": "#262628",
                "l-fg": "#fff", "r-bg": "var(--ios-r, #0a84ff)", "r-fg": "#fff", "link": "#4da3ff", "r-link": "#fff",
                "link-dec": "underline", "meta": "#8e8e93", "muted": "#8e8e93", "chip-bg": "transparent",
                "radius": "18px", "gap": "3px", "fs": "16px", "in-bg": "#000", "in-icon": "#8e8e93",
                "field": "#000", "card-bg": "#262628", "card-fg": "#fff", "card-border": "transparent",
                "call-bg": "#3a3a3c", "react-bg": "#262628", "av-disp": "none"})),
    "android": (
        dict(**{"chat-bg": "#fdfcff", "fg": "#1b1b1f", "sb-bg": "#fdfcff", "sb-fg": "#1b1b1f", "hdr-bg": "#fdfcff",
                "hdr-fg": "#1b1b1f", "hdr-icon": "#44474f", "hdr-border": "#e3e2e6", "av": "#7c6fd6", "l-bg": "#e8edf7",
                "l-fg": "#1b1b1f", "r-bg": "#d3e3fd", "r-fg": "#041e49", "link": "#0b57d0", "link-dec": "underline",
                "meta": "#5f6368", "muted": "#5f6368", "chip-bg": "transparent", "radius": "20px", "gap": "4px",
                "fs": "15.5px", "in-bg": "#fdfcff", "in-icon": "#44474f", "field": "#eef1f8", "card-bg": "#e8edf7",
                "card-fg": "#1b1b1f", "card-border": "transparent", "call-bg": "#fff", "react-bg": "#fff"}),
        dict(**{"chat-bg": "#131314", "fg": "#e3e3e3", "sb-bg": "#131314", "sb-fg": "#e3e3e3", "hdr-bg": "#131314",
                "hdr-fg": "#e3e3e3", "hdr-icon": "#c4c7c5", "hdr-border": "#2a2a2c", "av": "#5e54a8", "l-bg": "#2b2c30",
                "l-fg": "#e3e3e3", "r-bg": "#0842a0", "r-fg": "#d3e3fd", "link": "#a8c7fa", "link-dec": "underline",
                "meta": "#9aa0a6", "muted": "#9aa0a6", "chip-bg": "transparent", "radius": "20px", "gap": "4px",
                "fs": "15.5px", "in-bg": "#131314", "in-icon": "#c4c7c5", "field": "#1e1f20", "card-bg": "#2b2c30",
                "card-fg": "#e3e3e3", "card-border": "transparent", "call-bg": "#1e1f20", "react-bg": "#2b2c30"})),
    "telegram": (
        dict(**{"chat-bg": "#cfe3b4", "wall": "linear-gradient(160deg,#d5e6b0,#9fc79b 55%,#b8d6a2)", "fg": "#000",
                "sb-bg": "#f7f7f7", "sb-fg": "#000", "hdr-bg": "#f7f7f7", "hdr-fg": "#000", "hdr-icon": "#3390ec",
                "hdr-border": "#d9d9d9", "av": "#e17076", "l-bg": "#fff", "l-fg": "#000", "r-bg": "#effedd",
                "r-fg": "#000", "link": "#3390ec", "r-link": "#3a8f2d", "meta": "#9aa3ad", "r-meta": "#5fa154",
                "muted": "#8d969c", "chip-bg": "rgba(70,110,60,.45)", "chip-fg": "#fff", "radius": "14px",
                "gap": "4px", "fs": "15.5px", "pad": "6px 10px 6px 11px", "in-bg": "#fff", "in-icon": "#8d969c",
                "field": "#fff", "card-bg": "#fff", "card-fg": "#000", "card-border": "transparent",
                "call-bg": "#fdecec", "react-bg": "#fff"}),
        dict(**{"chat-bg": "#0e1621", "wall": "linear-gradient(160deg,#0f1a24,#17212b 60%,#0e1621)", "fg": "#f5f5f5",
                "sb-bg": "#17212b", "sb-fg": "#f5f5f5", "hdr-bg": "#17212b", "hdr-fg": "#f5f5f5", "hdr-icon": "#6ab2f2",
                "hdr-border": "#101921", "av": "#c25c62", "l-bg": "#182533", "l-fg": "#f5f5f5", "r-bg": "#2b5278",
                "r-fg": "#f5f5f5", "link": "#71baf8", "r-link": "#9fd2ff", "meta": "#6d7f8f", "r-meta": "#7da8d3",
                "muted": "#6d7f8f", "chip-bg": "rgba(0,0,0,.35)", "chip-fg": "#e8e8e8", "radius": "14px",
                "gap": "4px", "fs": "15.5px", "pad": "6px 10px 6px 11px", "in-bg": "#17212b", "in-icon": "#6d7f8f",
                "field": "#17212b", "card-bg": "#182533", "card-fg": "#f5f5f5", "card-border": "transparent",
                "call-bg": "#24303d", "react-bg": "#182533"})),
    "viber": (
        dict(**{"chat-bg": "#f4f3f8", "fg": "#1a1a1a", "sb-bg": "#7360f2", "sb-fg": "#fff", "hdr-bg": "#7360f2",
                "hdr-fg": "#fff", "hdr-icon": "#fff", "hdr-border": "#7360f2", "av": "#f2a65a", "l-bg": "#fff",
                "l-fg": "#1a1a1a", "r-bg": "#e2dcfd", "r-fg": "#1a1a1a", "link": "#665cac", "link-dec": "underline",
                "meta": "#8f8f9d", "muted": "#8f8f9d", "chip-bg": "rgba(0,0,0,.08)", "radius": "16px", "gap": "5px",
                "fs": "15px", "in-bg": "#fff", "in-icon": "#7360f2", "field": "#f1f1f4", "card-bg": "#fff",
                "card-fg": "#1a1a1a", "card-border": "transparent", "call-bg": "#fdecec", "react-bg": "#fff"}),
        dict(**{"chat-bg": "#121216", "fg": "#ececf1", "sb-bg": "#1f1d2b", "sb-fg": "#fff", "hdr-bg": "#1f1d2b",
                "hdr-fg": "#fff", "hdr-icon": "#b3a7ff", "hdr-border": "#1f1d2b", "av": "#a86b32", "l-bg": "#26262e",
                "l-fg": "#ececf1", "r-bg": "#3e3577", "r-fg": "#f1eeff", "link": "#b3a7ff", "link-dec": "underline",
                "meta": "#8c8c99", "muted": "#8c8c99", "chip-bg": "rgba(255,255,255,.08)", "radius": "16px",
                "gap": "5px", "fs": "15px", "in-bg": "#1a1a20", "in-icon": "#b3a7ff", "field": "#26262e",
                "card-bg": "#26262e", "card-fg": "#ececf1", "card-border": "transparent", "call-bg": "#3a2326",
                "react-bg": "#26262e"})),
    "whatsapp": (
        dict(**{"chat-bg": "#efeae2", "wall": "radial-gradient(circle at 20% 30%,#e7e0d6 0 2px,transparent 3px) 0 0/34px 34px,"
                                              "radial-gradient(circle at 70% 80%,#e6ded3 0 2px,transparent 3px) 0 0/41px 41px,#efeae2",
                "fg": "#111b21", "sb-bg": "#008069", "sb-fg": "#fff", "hdr-bg": "#008069", "hdr-fg": "#fff",
                "hdr-icon": "#fff", "hdr-border": "#008069", "av": "#25a28a", "l-bg": "#fff", "l-fg": "#111b21",
                "r-bg": "#d9fdd3", "r-fg": "#111b21", "link": "#027eb5", "meta": "#667781", "muted": "#667781",
                "chip-bg": "#fff", "chip-fg": "#54656f", "radius": "8px", "gap": "3px", "fs": "15px",
                "pad": "6px 8px 7px 9px", "in-bg": "#efeae2", "in-icon": "#54656f", "field": "#fff",
                "card-bg": "#fff", "card-fg": "#111b21", "card-border": "transparent", "call-bg": "#fdecec",
                "react-bg": "#fff", "av-disp": "none"}),
        dict(**{"chat-bg": "#0b141a", "wall": "radial-gradient(circle at 20% 30%,#121c22 0 2px,transparent 3px) 0 0/34px 34px,#0b141a",
                "fg": "#e9edef", "sb-bg": "#1f2c34", "sb-fg": "#e9edef", "hdr-bg": "#1f2c34", "hdr-fg": "#e9edef",
                "hdr-icon": "#aebac1", "hdr-border": "#1f2c34", "av": "#1f7a68", "l-bg": "#202c33", "l-fg": "#e9edef",
                "r-bg": "#005c4b", "r-fg": "#e9edef", "link": "#53bdeb", "meta": "#8696a0", "r-meta": "#9fc7bf",
                "muted": "#8696a0", "chip-bg": "#182229", "chip-fg": "#8696a0", "radius": "8px", "gap": "3px",
                "fs": "15px", "pad": "6px 8px 7px 9px", "in-bg": "#0b141a", "in-icon": "#8696a0", "field": "#1f2c34",
                "card-bg": "#202c33", "card-fg": "#e9edef", "card-border": "transparent", "call-bg": "#2a3942",
                "react-bg": "#202c33", "av-disp": "none"})),
    "web": (
        dict(**{"chat-bg": "#eef0f1", "fg": "#081c36", "rail": "#0068ff", "side-bg": "#fff", "side-act": "#e5efff",
                "hdr-bg": "#fff", "hdr-fg": "#081c36", "hdr-icon": "#495667", "hdr-border": "#dfe2e7", "av": "#6aa4f0",
                "l-bg": "#fff", "l-fg": "#081c36", "r-bg": "#e5efff", "r-fg": "#081c36", "rb-border": "1px solid #c7dbfa",
                "link": "#0068ff", "meta": "#7589a3", "muted": "#7589a3", "chip-bg": "rgba(0,0,0,.1)",
                "radius": "8px", "gap": "8px", "fs": "14.5px", "maxw": "62%", "in-bg": "#fff", "in-icon": "#495667",
                "field": "#fff", "card-bg": "#fff", "card-fg": "#081c36", "card-border": "#dfe2e7",
                "call-bg": "#fdecec", "react-bg": "#fff", "sb-bg": "#fff", "sb-fg": "#000"}),
        dict(**{"chat-bg": "#16171a", "fg": "#e4e6eb", "rail": "#0b3a7a", "side-bg": "#1f2023", "side-act": "#2c3440",
                "hdr-bg": "#1f2023", "hdr-fg": "#e4e6eb", "hdr-icon": "#b0b3b8", "hdr-border": "#2d2e31", "av": "#3b6fb6",
                "l-bg": "#2a2b2e", "l-fg": "#e4e6eb", "r-bg": "#1c3b66", "r-fg": "#e8f0fb", "link": "#5aa2ff",
                "meta": "#8a8f98", "muted": "#8a8f98", "chip-bg": "rgba(255,255,255,.08)", "radius": "8px",
                "gap": "8px", "fs": "14.5px", "maxw": "62%", "in-bg": "#1f2023", "in-icon": "#b0b3b8",
                "field": "#1f2023", "card-bg": "#2a2b2e", "card-fg": "#e4e6eb", "card-border": "#3a3b3e",
                "call-bg": "#3a2326", "react-bg": "#2a2b2e", "sb-bg": "#1f2023", "sb-fg": "#fff"})),
}
TIME_MODE = {"zalo": "tm-below", "messenger": "tm-none", "imessage": "tm-none", "android": "tm-none",
             "telegram": "tm-inline", "viber": "tm-below", "whatsapp": "tm-inline", "web": "tm-below"}
SUBTITLE = {"zalo": ["Vừa truy cập", "Truy cập 5 phút trước", "Truy cập 1 giờ trước", ""],
            "messenger": ["Đang hoạt động", "Hoạt động 12 phút trước", "Hoạt động 1 giờ trước", ""],
            "telegram": ["truy cập gần đây", "online", "last seen recently", "truy cập lúc 21:40"],
            "viber": ["Online", "Truy cập 10 phút trước", ""],
            "whatsapp": ["online", "trực tuyến", "đang nhập...", ""],
            "web": ["Vừa truy cập", "Truy cập 3 phút trước", "Người lạ - Chưa là bạn bè"],
            "android": [""], "imessage": [""]}
FIELD = {"zalo": "Tin nhắn", "messenger": "Nhắn tin", "imessage": "iMessage", "android": "Tin nhắn văn bản",
         "telegram": "Tin nhắn", "viber": "Nhập tin nhắn...", "whatsapp": "Tin nhắn",
         "web": "Nhập @, tin nhắn tới"}
CALL_TEXT = {"zalo": ("Bạn bị nhỡ cuộc gọi thoại", "Gọi lại"), "messenger": ("Bạn đã bỏ lỡ cuộc gọi thoại", "Gọi lại"),
             "imessage": ("Cuộc gọi FaceTime bị nhỡ", "Gọi lại"), "android": ("Cuộc gọi nhỡ", "Gọi lại"),
             "telegram": ("Cuộc gọi nhỡ", "Cuộc gọi đến"), "viber": ("Cuộc gọi nhỡ", "Viber Out"),
             "whatsapp": ("Cuộc gọi thoại bị nhỡ", "Nhấn để gọi lại"), "web": ("Bạn bị nhỡ cuộc gọi video", "Gọi lại")}
CALL_TEXT_VIDEO = ("Bạn đã bỏ lỡ cuộc gọi video", "Gọi lại")
BANK_COLORS = ["#0f7a3b", "#e2231a", "#1a4795", "#00a650", "#7b2c8e", "#f37021", "#0d5c9e", "#004b8d", "#ac1f2d"]


def initials(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[:1].isalpha()]
    if not words:
        return "?"
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()


def render_parts(parts, strings) -> str:
    out = []
    for p in parts:
        if p[0] == "t":
            out.append(html.escape(p[1]))
        elif p[0] == "br":
            out.append("\n")
        elif p[0] == "s":
            s = strings[p[1]]
            cls = "s link" if s["type"] == "link" else "s"
            out.append(f'<span class="{cls}" data-sid="{p[1]}">{html.escape(s["raw"])}</span>')
        elif p[0] == "b":
            out.append(f'<span data-bank="1">{html.escape(p[1])}</span>')
        elif p[0] == "h":
            out.append(f'<span data-holder="1">{html.escape(p[1])}</span>')
    return "".join(out)


def status_bar(spec) -> str:
    t = spec["clock"]
    android = spec["template"] in ("android",) or spec["os"] == "android"
    bars = "".join(f'<span class="bar" style="height:{h}px"></span>' for h in (4, 6, 8, 10))
    net = '<span style="font-size:11px;margin-right:3px">4G</span>' if android or spec["vis"]["net4g"] else ""
    return (f'<div class="status" style="{"padding:0 16px;font-size:13px" if android else ""}"><span>{t}</span>'
            f'<span class="ic">{net}{bars}<span class="batt" style="--batt:{spec["vis"]["batt"]}%"></span></span></div>')


def header(spec) -> str:
    tpl, name, v = spec["template"], html.escape(spec["contact"]), spec["vis"]
    ini = html.escape(initials(spec["contact"]))
    sub = html.escape(v["subtitle"])
    av = f'<div class="hav{" on" if v["online"] and tpl == "messenger" else ""}" style="background:{v["avc"]}">{ini}</div>'
    if tpl == "imessage":
        return (f'<div class="header"><div class="back">{icon("back", 24)}<span>{v["unread"] or ""}</span></div>'
                f'<div class="vid">{icon("video", 24)}</div>{av}<div class="nm">{name} ›</div></div>')
    icons = {"zalo": ["phone", "video", "menu"], "messenger": ["phone", "video", "info"], "android": ["phone", "dots"],
             "telegram": ["dots"], "viber": ["phone", "video", "dots"], "whatsapp": ["video", "phone", "dots"],
             "web": ["search", "video", "info"]}[tpl]
    ic = "".join(icon(i, 22) for i in icons)
    back = "" if tpl == "web" else icon("back", 24)
    who = f'<div class="who"><b>{name}</b>{f"<small>{sub}</small>" if sub else ""}</div>'
    if tpl == "telegram" and spec["os"] == "ios":
        return f'<div class="header">{back}<div class="who" style="align-items:center"><b>{name}</b><small>{sub}</small></div>{av}</div>'
    if tpl == "zalo":
        return f'<div class="header">{back}{who}<div class="icons">{ic}</div></div>'
    return f'<div class="header">{back}{av}{who}<div class="icons">{ic}</div></div>'


def input_bar(spec) -> str:
    tpl = spec["template"]
    f = FIELD[tpl]
    if tpl == "zalo":
        return (f'<div class="input">{icon("smile")}<div class="field" style="background:transparent;padding:0">{f}</div>'
                f'{icon("dots")}{icon("mic")}{icon("img")}</div>')
    if tpl == "messenger":
        return (f'<div class="input">{icon("plus")}{icon("cam")}{icon("img")}{icon("mic")}'
                f'<div class="field">{f}</div>{icon("like")}</div>')
    if tpl == "imessage":
        return (f'<div class="input"><span style="font-size:26px;line-height:1">+</span>'
                f'<div class="field" style="border:1px solid #8e8e9355">{f}</div></div>')
    if tpl == "android":
        return f'<div class="input">{icon("plus")}<div class="field">{f}</div>{icon("img")}{icon("mic")}</div>'
    if tpl == "telegram":
        return f'<div class="input">{icon("clip")}<div class="field">{f}</div>{icon("smile")}{icon("mic")}</div>'
    if tpl == "viber":
        return f'<div class="input">{icon("plus")}<div class="field">{f}</div>{icon("smile")}{icon("send")}</div>'
    if tpl == "whatsapp":
        return (f'<div class="input" style="border:none">{icon("smile")}<div class="field">{f}</div>'
                f'{icon("clip")}{icon("cam")}<div style="width:42px;height:42px;border-radius:50%;background:#00a884;'
                f'color:#fff;display:flex;align-items:center;justify-content:center">{icon("mic", 20, "#fff")}</div></div>')
    return (f'<div class="input" style="flex-direction:column;align-items:stretch;gap:6px"><div style="display:flex;gap:14px">'
            f'{icon("smile", 20)}{icon("img", 20)}{icon("clip", 20)}</div><div class="field">{f} {html.escape(spec["contact"])}'
            f'</div></div>')


def item_html(spec, i: int, it: dict, strings: dict, prev_side) -> str:
    tpl, v = spec["template"], spec["vis"]
    kind = it["kind"]
    if kind == "chip":
        return f'<div class="chip" data-item="{i}">{render_parts(it["parts"], strings)}</div>'
    side = it.get("side", "left")
    cont = "cont" if side == prev_side and side == "left" and not it.get("first") else ""
    gap = "gap" if side != prev_side else ""
    ini = html.escape(initials(spec["contact"]))
    av = f'<div class="av" style="background:{v["avc"]}">{ini}</div>'
    meta = f'<span class="meta">{it.get("time", "")}{" ✓✓" if side == "right" and tpl in ("telegram", "whatsapp") else ""}</span>'
    if kind == "text":
        react = f'<span class="react">{it["react"]}</span>' if it.get("react") else ""
        body = (f'<div class="bubble {TIME_MODE[tpl]}" data-msg="{i}"><span class="txt">{render_parts(it["parts"], strings)}'
                f'</span>{meta}{react}</div>')
        tail = ""
        if tpl == "android" and it.get("tm_out"):
            tail = f'<div class="tm-out">{it.get("time", "")}</div>'
        return f'<div class="row {side} {cont} {gap}" data-item="{i}">{av}{body}</div>{tail}'
    if kind == "img":
        pw, ph = it["pw"], it["ph"]
        return (f'<div class="row {side} {cont} {gap}" data-item="{i}">{av}<div class="card media" style="--pw:{pw}px;--ph:{ph}px;'
                f'border:none"><div class="pic" style="background:{it["bg"]}"></div></div></div>')
    if kind == "lcard":
        return (f'<div class="row {side} {cont}" data-item="{i}">{av}<div class="card lcard"><div class="th" style="background:'
                f'{it["bg"]}"></div><div class="bd"><b>{html.escape(it["title"])}</b><small>{html.escape(it["desc"])}</small>'
                f'<i>{html.escape(it["site"])}</i></div></div></div>')
    if kind == "call":
        t, sub = CALL_TEXT_VIDEO if it.get("video") else CALL_TEXT[tpl]
        return (f'<div class="row {side} {cont} {gap}" data-item="{i}">{av}<div class="card call"><div class="ci">'
                f'{icon("call_missed", 18, "#e5484d")}</div><div><b>{t}</b><small>{sub} · {it.get("time", "")}</small></div></div></div>')
    if kind == "receipt":
        r = it
        rows = [("Người nhận", f'<span data-holder="1">{html.escape(r["holder"])}</span>'),
                ("Tài khoản", render_parts([["s", r["acc"]]], strings)),
                ("Ngân hàng", f'<span data-bank="1">{html.escape(r["bank"])}</span>'),
                ("Nội dung", html.escape(r["memo"]))]
        if r.get("tx"):
            rows.append(("Mã giao dịch", render_parts([["s", r["tx"]]], strings)))
        if r.get("when"):
            rows.append(("Thời gian", render_parts([["s", r["when"]]], strings)))
        rows_html = "".join(f'<div class="r"><span>{a}</span><span>{b}</span></div>' for a, b in rows)
        amt = render_parts([["s", r["amt"]]], strings)
        return (f'<div class="row {side} {cont} {gap}" data-item="{i}">{av}<div class="card receipt"><div class="top" '
                f'style="background:{r["color"]}"><div class="ok">✓</div><b>{html.escape(r["title"])}</b>'
                f'<div class="amt">{r.get("sign", "")}{amt}</div></div><div class="rows">{rows_html}</div></div></div>')
    raise ValueError(kind)


def chat_html(spec, items: list[tuple[int, dict]]) -> str:
    strings = spec["strings"]
    out, prev = [], None
    for i, it in items:
        out.append(item_html(spec, i, it, strings, prev))
        prev = it.get("side") if it["kind"] != "chip" else None
    return f'<div class="chat"><div class="inner">{"".join(out)}</div></div>'


def web_sidebar(spec) -> str:
    v = spec["vis"]
    convs = [(spec["contact"], v["side_snip"], "act")] + [(n, s, "") for n, s in v["side_list"]]
    rows = []
    for k, (n, s, act) in enumerate(convs):
        col = v["side_cols"][k % len(v["side_cols"])]
        rows.append(f'<div class="conv {act}"><div class="hav" style="background:{col}">{html.escape(initials(n))}</div>'
                    f'<div class="cw"><b>{html.escape(n)}</b><small>{html.escape(s)}</small></div><em>{v["side_times"][k]}</em></div>')
    return (f'<div class="rail"><div class="me"></div>{icon("menu", 24, "#fff")}{icon("search", 24, "#fff")}</div>'
            f'<div class="side"><div class="sr"><div class="f">{icon("search", 16)}Tìm kiếm</div></div>{"".join(rows)}</div>')


def page_html(spec, items: list[tuple[int, dict]], screen: dict, long: bool = False) -> str:
    tpl, dark = spec["template"], spec["dark"]
    theme = {**COMMON, **THEMES[tpl][DARK if dark else LIGHT], "W": f'{screen["w"]}px', "H": f'{screen["h"]}px'}
    if spec["vis"].get("font"):
        theme["font"] = spec["vis"]["font"]
    if tpl == "imessage" and spec["vis"].get("sms_green"):
        theme["ios-r"] = "#34c759"
    vars_css = ";".join(f"--{k}:{v}" for k, v in theme.items())
    css = BASE_CSS + TPL_CSS[tpl]
    chat = chat_html(spec, items)
    if tpl == "web":
        body = f'<div class="screen">{web_sidebar(spec)}<div class="main">{header(spec)}{chat}{input_bar(spec)}</div></div>'
    else:
        nav = ""
        if spec["os"] == "android":
            nav = ('<div class="nav nav3"><span>|||</span><span>◯</span><span>‹</span></div>' if spec["vis"]["nav3"]
                   else '<div class="nav"><div class="gl"></div></div>')
        elif spec["vis"]["home_ind"]:
            nav = '<div class="nav"><div class="gl" style="width:134px"></div></div>'
        sb = status_bar(spec) if spec["vis"]["status"] else ""
        body = f'<div class="screen">{sb}{header(spec)}{chat}{input_bar(spec)}{nav}</div>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body class="{"long" if long else ""}" style="{vars_css}">{body}</body></html>')
