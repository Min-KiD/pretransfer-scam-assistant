"""Method A: pull account / phone / link / amount strings out of OCR text lines with regex."""
from __future__ import annotations

import re

from e1.scenarios import NORMALIZERS

TLDS = "top|xyz|vn|com|net|cc|vip|online|site|info|org|io|me|link|shop|store|club|asia|biz|app"
LINK_RE = re.compile(
    rf"(?:https?://)?(?:www\.)?(?:[A-Za-z0-9-]+\.)+(?:{TLDS})\b(?:/[A-Za-z0-9._~\-/?=&%#]*)?", re.I)
PHONE_RE = re.compile(r"(?<![\d+])(?:\+\s?84[\s.]?\d{3}|0\d{3})[\s.]?\d{3}[\s.]?\d{3}(?!\d)")
AMOUNT_RE = re.compile(
    r"(?<![\d.,])(?:\d+\s?tr\d?(?![a-zà-ỹ])|\d+(?:[.,]\d+)?\s?(?:k|triệu)(?![a-zà-ỹ])"
    r"|\d{1,3}(?:[.,]\d{3})+\s?(?:đồng|đ|vnđ|vnd|d)?(?![a-zà-ỹ])|\d+\s?(?:đồng|đ|vnđ|vnd)(?![a-zà-ỹ]))",
    re.I)
ACCOUNT_RE = re.compile(r"(?<![\d.,+])\d(?: ?\d){7,13}(?![\d.,])")


def extract(lines: list[str]) -> dict[str, list[str]]:
    """Return raw strings per type, in reading order, de-duplicated by normalized form."""
    found: dict[str, list[str]] = {"account": [], "phone": [], "link": [], "amount": []}
    seen: set[tuple[str, str]] = set()

    def add(typ: str, raw: str):
        raw = raw.strip()
        key = (typ, NORMALIZERS[typ](raw))
        if key not in seen:
            seen.add(key)
            found[typ].append(raw)

    for line in lines:
        rest = line
        for typ, rx in (("link", LINK_RE), ("phone", PHONE_RE), ("amount", AMOUNT_RE), ("account", ACCOUNT_RE)):
            def sub(m, typ=typ):
                raw = m.group(0)
                if typ == "link" and "/" not in raw and not raw.lower().startswith("http"):
                    return raw  # bare "word.vn" without path: too ambiguous, leave it
                if typ == "account" and not 8 <= len(re.sub(r"\D", "", raw)) <= 14:
                    return raw
                add(typ, raw)
                return " " * len(raw)
            rest = rx.sub(sub, rest)
    return found
