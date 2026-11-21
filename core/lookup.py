"""Lookup tools (design doc 5.6) on self-made sample data. In MoMo these would call MoMo's own data.

Sample accounts use the prefix 000 so they cannot be real bank account numbers; holders are invented.
"""
from __future__ import annotations

SEED_ACCOUNTS = [
    # number, bank, holder, loai, nhan
    ("000123450001", "Vietcombank", "NGUYEN THI HOA", "ca_nhan", "quen"),
    ("000123450002", "Techcombank", "CONG TY TNHH THOI TRANG MAI ANH", "to_chuc", "quen"),
    ("000123450003", "MB Bank", "TRAN VAN BINH", "ca_nhan", "quen"),
    ("000123450004", "ACB", "LE MINH TUAN", "ca_nhan", "moi"),
    ("000123450005", "VPBank", "CONG TY CP GIAO HANG NHANH MIEN NAM", "to_chuc", "moi"),
    ("000123450006", "BIDV", "PHAM THI THU", "ca_nhan", "moi"),
    ("000123450007", "Sacombank", "DO VAN KHANH", "ca_nhan", "dang_bi_bao_cao"),
    ("000123450008", "VietinBank", "HOANG THI LAN", "ca_nhan", "dang_bi_bao_cao"),
    ("000123450009", "TPBank", "VU DUC MANH", "ca_nhan", "dang_bi_bao_cao"),
    ("000123450010", "Agribank", "NGO THI BICH", "ca_nhan", "da_xac_nhan"),
    ("000123450011", "SHB", "BUI VAN TOAN", "ca_nhan", "da_xac_nhan"),
    ("000123450012", "OCB", "CONG TY TNHH DAU TU TAI CHINH SAO VANG", "to_chuc", "da_xac_nhan"),
]

# Self-styled identities that are organisations: money for them should go to an organisation account.
ORG_ROLES = {"shipper", "cong_an", "ngan_hang", "co_quan_nha_nuoc", "nha_tuyen_dung", "san_dau_tu",
             "dich_vu_thu_hoi_tien"}

WARNING = {"da_xac_nhan": "do", "dang_bi_bao_cao": "vang", "moi": None, "quen": None}
CHAT = {"da_xac_nhan": "bat_luon", "dang_bi_bao_cao": "bat_luon", "moi": "moi_kiem_tra", "quen": "khong"}


def ten_khop_tu_xung(loai: str | None, tu_xung: str | None) -> str | None:
    """co/khong when the account type settles it, else None (unknown). A person's account for someone claiming to be
    a delivery company, the police or a bank does not match; an organisation account for an organisation role does."""
    if not loai or not tu_xung or tu_xung not in ORG_ROLES:
        return None
    return "co" if loai == "to_chuc" else "khong"


def normalise_account(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())
