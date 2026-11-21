"""Fake Vietnamese chat content for E1. Every number, name and domain is random and made up.

A message template is a string with placeholders `[[type:key]]`, where type is one of
account / phone / link / amount and key indexes the per-image value table. `\n` is a line break.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

TYPES = ("account", "phone", "link", "amount")

SCENARIOS = {
    1: "gia_shipper",
    2: "gia_cong_an",
    3: "ctv_nap_tien",
    4: "chuyen_nham",
    5: "binh_thuong",
}

BANKS = ["Vietcombank", "Techcombank", "MB Bank", "VPBank", "ACB", "BIDV", "VietinBank",
         "Sacombank", "TPBank", "Agribank", "VIB", "SHB"]
HO = ["NGUYEN", "TRAN", "LE", "PHAM", "HOANG", "HUYNH", "VO", "DANG", "BUI", "DO", "NGO", "DUONG"]
DEM = ["VAN", "THI", "DUC", "MINH", "THANH", "NGOC", "QUOC", "HOAI", "XUAN", "KIM"]
TEN = ["HUNG", "LAN", "TUAN", "HOA", "LONG", "TRANG", "DUNG", "PHUONG", "KHANH", "NAM", "LINH",
       "QUANG", "THAO", "HIEU", "VY"]
CONTACTS = {
    1: ["Giao Hàng Nhanh 24h", "Shipper Tuấn", "Bưu cục Q.7", "Giao hàng - Hưng"],
    2: ["Cán bộ Trần Minh", "Đội điều tra PC02", "Số lạ", "Công an phường"],
    3: ["CSKH Tuyển CTV", "Mai Anh - Tuyển dụng", "Nhiệm vụ Online", "HR Shop Online"],
    4: ["Ngọc Ánh", "Số lạ", "Em Hoa", "Linh Nguyễn"],
    5: ["Shop Quần Áo Minh Anh", "Chị Hạnh bán hàng", "Tiệm Bánh Nhà Mây", "Shop Giày Bảo"],
}
LINK_BASES = {
    1: [("giaohang-tietkiem-vn.top", "don"), ("ghn-express-vn.xyz", "tracking"),
        ("vnpost-phigiao.cc", "dh"), ("giaohangnhanh-cod.vip", "don")],
    2: [("dichvucong-bocongan.top", "khaibao"), ("congan-xacminh.vip", "hs"),
        ("cong-an-truc-tuyen.xyz", "tk")],
    3: [("nhiemvu-shopee-ctv.xyz", "reg"), ("tiktok-hoahong.top", "ctv"),
        ("lazada-nhiemvu.online", "task")],
    4: [("saoke-vietcombank.top", "gd"), ("mbbank-hoantien.xyz", "gd"),
        ("hoantien-nganhang.cc", "sk")],
    5: [("shopquanao-minhanh.vn", "sp"), ("tiembanh-nhamay.vn", "menu"),
        ("giaybao-store.vn", "sp")],
}
DISTRICTS = ["Hoàn Kiếm", "Cầu Giấy", "Đống Đa", "Quận 1", "Quận 3", "Bình Thạnh", "Hải Châu", "Ninh Kiều"]
MOBILE_PREFIX = ["090", "091", "093", "094", "096", "097", "098", "086", "088", "089",
                 "070", "076", "077", "078", "079", "081", "082", "083", "084", "085", "032",
                 "033", "034", "035", "036", "037", "038", "039", "056", "058", "059"]

# Each scenario: list of (side, required, [alternative templates]). Required messages hold targets.
DIALOGS = {
    1: [
        ("left", False, ["Chào anh/chị, em bên giao hàng, đơn của mình đang ở bưu cục ạ",
                         "Alo chị ơi, em shipper đây ạ, đơn hàng của chị tới rồi"]),
        ("right", False, ["Đơn gì vậy em? Chị chưa đặt gì cả", "Đơn nào thế em?"]),
        ("left", True, ["Đơn COD có phí giao hàng [[amount:a1]], mình chuyển khoản giúp em để em giao luôn ạ",
                        "Đơn bị thiếu phí vận chuyển [[amount:a1]] ạ, chị chuyển giúp em nhé"]),
        ("left", True, ["STK [[account:acc]]\n[[bank]]\n[[holder]]",
                        "Chị chuyển vào [[bank]] [[account:acc]] - [[holder]] giúp em"]),
        ("left", True, ["Chị tra cứu đơn tại [[link:l1]] nhé", "Link kiểm tra đơn: [[link:l1]]"]),
        ("right", True, ["Em gọi chị số này được không [[phone:p1]]", "Số chị là [[phone:p1]], gọi chị đi"]),
        ("left", False, ["Mình chuyển trước 18h giúp em, quá giờ đơn bị hoàn ạ"]),
        ("right", False, ["Ok để chị xem", "Chị kiểm tra lại đã"]),
    ],
    2: [
        ("left", False, ["Tôi là cán bộ Công an [[district]], đang điều tra vụ rửa tiền liên quan đến tài khoản của anh"]),
        ("right", False, ["Sao lại liên quan đến tôi?", "Tôi không biết gì cả"]),
        ("left", True, ["Anh phải chuyển [[amount:a1]] vào tài khoản an toàn để chứng minh nguồn tiền",
                        "Yêu cầu anh chuyển toàn bộ [[amount:a1]] vào tài khoản tạm giữ của cơ quan"]),
        ("left", True, ["Tài khoản tạm giữ: [[account:acc]]\n[[bank]] - [[holder]]",
                        "TK an toàn: [[account:acc]] ([[bank]]) chủ TK [[holder]]"]),
        ("left", True, ["Khai báo tại cổng [[link:l1]] trước 17h hôm nay", "Truy cập [[link:l1]] để khai báo"]),
        ("left", True, ["Liên hệ điều tra viên: [[phone:p1]]", "Gọi ngay cho đồng chí Hùng [[phone:p1]]"]),
        ("right", False, ["Tôi cần xác minh lại với công an phường", "Để tôi hỏi người nhà đã"]),
        ("left", False, ["Không được nói với ai, nếu không sẽ bị khởi tố vì cản trở điều tra"]),
    ],
    3: [
        ("left", False, ["Chào bạn, bên mình tuyển cộng tác viên làm nhiệm vụ online, hoa hồng 10-15%"]),
        ("right", False, ["Làm như thế nào vậy ạ?", "Việc gì thế bạn?"]),
        ("left", True, ["Bạn đăng ký tại [[link:l1]] rồi nạp [[amount:a1]] để nhận nhiệm vụ đầu tiên"]),
        ("left", True, ["Nạp vào STK [[account:acc]] [[bank]]\nChủ TK: [[holder]]",
                        "[[bank]]\n[[account:acc]]\n[[holder]]"]),
        ("right", False, ["Nạp xong thì bao giờ được rút?"]),
        ("left", True, ["Hoàn thành 3 nhiệm vụ nhận ngay [[amount:a2]], cần hỗ trợ gọi [[phone:p1]]",
                        "Xong nhiệm vụ rút được [[amount:a2]], zalo hỗ trợ [[phone:p1]]"]),
        ("right", False, ["Mình nạp ít trước được không", "Ok mình thử"]),
        ("left", False, ["Được bạn nhé, nhanh giúp mình kẻo hết suất hôm nay"]),
    ],
    4: [
        ("left", True, ["Chị ơi em chuyển nhầm [[amount:a1]] vào tài khoản của chị, chị kiểm tra giúp em",
                        "Anh ơi em lỡ chuyển nhầm [[amount:a1]] cho anh ạ"]),
        ("right", False, ["Để chị xem lại", "Ừ để anh kiểm tra"]),
        ("left", True, ["Chuyển lại giúp em vào tài khoản của mẹ em: [[account:acc]] [[bank]] [[holder]]",
                        "Hoàn giúp em vào STK [[account:acc]]\n[[bank]] - [[holder]] nhé"]),
        ("right", False, ["Sao không chuyển lại vào tài khoản gốc?"]),
        ("left", True, ["Tài khoản em bị khóa rồi, sao kê ở đây [[link:l1]]", "Em gửi sao kê: [[link:l1]]"]),
        ("left", True, ["Gấp lắm, em gọi nhé [[phone:p1]]", "Số em đây [[phone:p1]], có gì gọi em"]),
        ("right", False, ["Chị sẽ liên hệ ngân hàng trước", "Để mai anh ra ngân hàng hỏi"]),
        ("left", False, ["Chuyển giúp em sớm nhé, em cảm ơn nhiều"]),
    ],
    5: [
        ("left", True, ["Chào chị, đơn 2 áo thun size M của chị tổng [[amount:a1]] ạ",
                        "Dạ đơn bánh của chị hết [[amount:a1]] ạ"]),
        ("right", False, ["Ok em, gửi chị số tài khoản nhé"]),
        ("left", True, ["Dạ chị chuyển khoản giúp em: [[account:acc]] [[bank]] [[holder]]",
                        "STK: [[account:acc]]\n[[bank]]\nCTK: [[holder]]"]),
        ("left", True, ["Ảnh sản phẩm em để ở [[link:l1]] chị xem lại nhé", "Chị xem mẫu tại [[link:l1]] ạ"]),
        ("right", False, ["Chị chuyển rồi nha, ship về giúp chị trước thứ 7"]),
        ("left", True, ["Dạ em nhận được rồi, shipper sẽ gọi chị số [[phone:p1]] ạ",
                        "Có gì chị gọi em [[phone:p1]] nha"]),
        ("right", False, ["Cảm ơn em", "Ok em"]),
        ("left", False, ["Dạ phí ship [[amount:a2]] em hỗ trợ chị luôn ạ, cảm ơn chị"]),
    ],
}

AMOUNT_STYLES = ("dot_d", "dot_vnd", "tr", "k")
PHONE_STYLES = ("space", "dot", "intl", "plain")
CONFUSABLE = "0O1lI"
ALNUM = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class Target:
    type: str
    key: str
    raw: str
    norm: str
    extra: dict = field(default_factory=dict)


def norm_digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def norm_phone(s: str) -> str:
    d = norm_digits(s)
    if d.startswith("84") and len(d) == 11:
        d = "0" + d[2:]
    return d


def norm_link(s: str) -> str:
    s = s.strip().rstrip(".,;:!?)")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^(https?://)", "", s, flags=re.I)
    s = re.sub(r"^www\.", "", s, flags=re.I)
    host, sep, path = s.partition("/")
    return host.lower() + sep + path.rstrip("/")


def norm_amount(s: str) -> str:
    s = re.sub(r"\s+", "", s.strip()).lower()
    s = re.sub(r"(?<=\d)[.,](?=\d{3}(\D|$))", "", s)  # thousands separators only
    s = s.replace("vnđ", "vnd").replace("đồng", "đ")
    return s


NORMALIZERS = {"account": norm_digits, "phone": norm_phone, "link": norm_link, "amount": norm_amount}


def amount_value(s: str) -> int | None:
    """Parse an amount string to integer VND (secondary metric)."""
    t = re.sub(r"\s+", "", s.lower())
    m = re.fullmatch(r"(\d+)tr(\d*)", t)
    if m:
        frac = m.group(2)
        return int(m.group(1)) * 1_000_000 + (int(frac) * 10 ** (6 - len(frac)) if frac else 0)
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(k|triệu|tr)", t)
    if m:
        v = float(m.group(1).replace(",", "."))
        return int(round(v * (1000 if m.group(2) == "k" else 1_000_000)))
    m = re.fullmatch(r"(\d{1,3}(?:[.,]\d{3})+|\d+)(đ|d|vnd|vnđ|đồng)?", t)
    if m:
        return int(re.sub(r"\D", "", m.group(1)))
    return None


def fmt_amount(v: int, style: str) -> str:
    if style == "dot_d":
        return f"{v:,}".replace(",", ".") + "đ"
    if style == "dot_vnd":
        return f"{v:,}".replace(",", ".") + " VND"
    if style == "tr":
        tr, rest = divmod(v, 1_000_000)
        return f"{tr}tr" + (str(rest // 100_000) if rest else "")
    if style == "k":
        return f"{v // 1000}k"
    raise ValueError(style)


def gen_amount(rng: random.Random, scenario: int, style: str) -> str:
    if style == "tr":
        v = rng.randint(1, 9) * 1_000_000 + rng.choice([0, 1, 2, 3, 5, 8]) * 100_000
    elif style == "k":
        v = rng.choice([30, 35, 50, 99, 150, 200, 250] if scenario in (1, 5) else [300, 450, 500, 800, 900]) * 1000
    else:
        small = scenario in (1, 5)
        v = (rng.choice([25, 30, 32, 35, 42, 45, 50, 65]) * 1000 if small and rng.random() < 0.6
             else rng.choice([150, 280, 350, 500, 1500, 2500, 4800, 12000, 25000, 150000]) * 1000)
    return fmt_amount(v, style)


def gen_phone(rng: random.Random, style: str) -> str:
    d = rng.choice(MOBILE_PREFIX) + "".join(rng.choice("0123456789") for _ in range(7))
    a, b, c = d[:4], d[4:7], d[7:]
    if style == "space":
        return f"{a} {b} {c}"
    if style == "dot":
        return f"{a}.{b}.{c}"
    if style == "intl":
        return f"+84 {d[1:4]} {b} {c}"
    return d


def gen_account(rng: random.Random) -> str:
    n = rng.randint(8, 14)
    first = rng.choice("123456789")
    if n == 13 and rng.random() < 0.5:
        first = "0"  # some banks issue 13-digit numbers starting with 0
    d = first + "".join(rng.choice("0123456789") for _ in range(n - 1))
    if rng.random() < 0.45:
        return " ".join(d[i:i + 4] for i in range(0, n, 4))
    return d


def lookalike(rng: random.Random, host: str) -> str:
    name, _, tld = host.rpartition(".")
    swaps = [(i, ch) for i, ch in enumerate(name) if ch in "oil"]
    if swaps and rng.random() < 0.6:
        i, ch = rng.choice(swaps)
        name = name[:i] + {"o": "0", "i": "1", "l": "1"}[ch] + name[i + 1:]
    elif "m" in name and rng.random() < 0.3:
        name = name.replace("m", "rn", 1)
    return f"{name}.{tld}"


def gen_link(rng: random.Random, scenario: int) -> str:
    host, seg = rng.choice(LINK_BASES[scenario])
    if scenario != 5:
        host = lookalike(rng, host)
    code_len = rng.randint(4, 6)
    code = "".join(rng.choice(CONFUSABLE) if rng.random() < 0.35 else rng.choice(ALNUM) for _ in range(code_len))
    prefix = rng.choice(["", "", "https://"])
    return f"{prefix}{host}/{seg}/{code}"


def gen_holder(rng: random.Random) -> str:
    parts = [rng.choice(HO), rng.choice(DEM), rng.choice(TEN)]
    if rng.random() < 0.3:
        parts.insert(2, rng.choice(DEM))
    return " ".join(parts)


@dataclass
class Conversation:
    scenario: int
    contact: str
    messages: list  # [(side, template)]
    targets: dict   # key -> Target
    fills: dict     # placeholder -> plain text (bank, holder, district)


def build(rng: random.Random, scenario: int, n_msgs: int) -> Conversation:
    dialog = DIALOGS[scenario]
    targets: dict[str, Target] = {}
    acc = gen_account(rng)
    bank = rng.choice(BANKS)
    holder = gen_holder(rng)
    targets["acc"] = Target("account", "acc", acc, norm_digits(acc), {"bank": bank, "holder": holder})
    p = gen_phone(rng, rng.choice(PHONE_STYLES))
    targets["p1"] = Target("phone", "p1", p, norm_phone(p))
    link = gen_link(rng, scenario)
    targets["l1"] = Target("link", "l1", link, norm_link(link))
    styles = rng.sample(AMOUNT_STYLES, 2)
    for key, st in zip(("a1", "a2"), styles):
        a = gen_amount(rng, scenario, st)
        targets[key] = Target("amount", key, a, norm_amount(a))
    fills = {"bank": bank, "holder": holder, "district": rng.choice(DISTRICTS)}

    required = [i for i, (_, req, _) in enumerate(dialog) if req]
    optional = [i for i, (_, req, _) in enumerate(dialog) if not req]
    n = max(len(required), min(n_msgs, len(dialog)))
    chosen = set(required)
    rights = [i for i in optional if dialog[i][0] == "right"]
    if not any(dialog[i][0] == "right" for i in chosen) and rights:
        chosen.add(rng.choice(rights))
    rest = [i for i in optional if i not in chosen]
    rng.shuffle(rest)
    chosen.update(rest[: max(0, n - len(chosen))])
    msgs = [(dialog[i][0], rng.choice(dialog[i][2])) for i in sorted(chosen)]
    used = set(re.findall(r"\[\[\w+:(\w+)\]\]", "".join(t for _, t in msgs)))
    targets = {k: v for k, v in targets.items() if k in used}
    return Conversation(scenario, rng.choice(CONTACTS[scenario]), msgs, targets, fills)


SEG_RE = re.compile(r"\[\[(\w+)(?::(\w+))?\]\]")


def segments(template: str, conv: Conversation):
    """Yield ('text', str) / ('target', Target) / ('br', None)."""
    for line_i, line in enumerate(template.split("\n")):
        if line_i:
            yield ("br", None)
        pos = 0
        for m in SEG_RE.finditer(line):
            if m.start() > pos:
                yield ("text", line[pos:m.start()])
            kind, key = m.group(1), m.group(2)
            if key:
                yield ("target", conv.targets[key])
            else:
                yield ("text", conv.fills[kind])
            pos = m.end()
        if pos < len(line):
            yield ("text", line[pos:])


def plain_text(template: str, conv: Conversation) -> str:
    out = []
    for kind, val in segments(template, conv):
        out.append("\n" if kind == "br" else val.raw if kind == "target" else val)
    return "".join(out)
