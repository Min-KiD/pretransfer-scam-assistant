"""Story table ("bảng câu chuyện"), design doc section 5.2.

Every field has a closed value list that always ends with `khac`. A single-select field holds one value or None;
a multi-select field holds a list of values (empty list = unknown). Besides the scored fields the table keeps
`bang_chung` (where each value came from), `khong_chac` (fields whose sources disagree; not scored until the user
confirms) and `chuoi_trich` (strings read from images: accounts, phones, links, amounts).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    values: tuple[str, ...]  # always ends with "khac"
    multi: bool = False
    code_filled: bool = False  # filled by lookups / code, never asked
    image_checkable: bool = False  # can be read from a chat screenshot (tie-break rule in 5.4)
    label: str = ""  # short Vietnamese description, used in prompts and the UI


def _f(name, values, label, multi=False, code=False, image=False):
    return Field(name, tuple(values) + ("khac",), multi, code, image, label)


CO_KHONG = ("co", "khong")
FIELDS: dict[str, Field] = {f.name: f for f in (
    _f("nguoi_lien_lac", ("nguoi_la", "nguoi_quen", "tu_tim_den"),
       "người nhận tiền là người lạ, người quen, hay do mình tự tìm đến"),
    _f("kenh", ("cuoc_goi", "sms", "zalo", "messenger", "telegram", "truc_tiep"),
       "liên lạc qua kênh nào", image=True),
    _f("tu_xung", ("shipper", "cong_an", "ngan_hang", "co_quan_nha_nuoc", "nguoi_than", "nguoi_ban", "nha_tuyen_dung",
                   "san_dau_tu", "giao_vien_y_te", "dich_vu_thu_hoi_tien", "nguoi_chuyen_nham"),
       "người kia tự xưng là ai (cong_an gồm viện kiểm sát, tòa án; co_quan_nha_nuoc gồm thuế, điện lực, VNeID; "
       "nguoi_than gồm bạn bè, cấp trên)", image=True),
    _f("ai_bat_dau", ("ho_truoc", "minh_truoc"), "ai liên lạc trước", image=True),
    _f("ap_luc", ("hoi_thuc", "doa", "hua_loi", "giu_bi_mat", "khong_co"),
       "người kia có hối thúc, dọa, hứa lợi, bảo giữ bí mật không", multi=True, image=True),
    _f("yeu_cau", ("chuyen_tien", "cai_app", "doc_otp", "bam_link", "nap_them_de_rut", "lien_he_so_ho_dua"),
       "người kia yêu cầu làm gì", multi=True, image=True),
    _f("ly_do_tien", ("phi", "dat_coc", "tai_khoan_an_toan", "hoan_tien", "dau_tu", "tra_hang", "muon_tien",
                      "vien_phi", "nhiem_vu", "khac_phuc_loi"),
       "lý do phải chuyển tiền (khac_phuc_loi gồm hủy đăng ký, sửa lỗi giao dịch, mở khóa, xác minh)", image=True),
    _f("loai_tai_khoan", ("ca_nhan", "to_chuc"), "tài khoản nhận là cá nhân hay tổ chức", code=True),
    _f("ten_khop_tu_xung", CO_KHONG, "tên chủ tài khoản có khớp với người/tổ chức họ tự xưng không", code=True),
    _f("da_gap_truc_tiep", CO_KHONG, "đã gặp trực tiếp người nhận tiền chưa"),
    _f("duoc_dan_cach_tra_loi", CO_KHONG, "có ai dặn trước phải trả lời thế nào nếu bị hỏi không"),
    _f("da_chuyen_truoc_do", CO_KHONG, "đã chuyển cho chính người/nhóm này trước đó, giờ bị đòi chuyển thêm"),
    _f("mau_thuan_loi_ke_va_anh", CO_KHONG, "lời kể và ảnh có mâu thuẫn nhau không", code=True),
    _f("nhan_tai_khoan", ("quen", "moi", "dang_bi_bao_cao", "da_xac_nhan"), "nhãn của tài khoản nhận", code=True),
)}
assert len(FIELDS) == 14
CODE_FIELDS = tuple(n for n, f in FIELDS.items() if f.code_filled)
ASKABLE = tuple(n for n, f in FIELDS.items() if not f.code_filled)
GROUPS = ("lua_dao", "binh_thuong")
STRING_TYPES = ("account", "phone", "link", "amount")


def empty_table() -> dict:
    t = {n: ([] if f.multi else None) for n, f in FIELDS.items()}
    t.update(bang_chung=[], khong_chac=[], chuoi_trich={k: [] for k in STRING_TYPES})
    return t


def is_filled(table: dict, name: str) -> bool:
    v = table.get(name)
    return bool(v) if FIELDS[name].multi else v is not None


def set_value(table: dict, name: str, value, source: str = "", quote: str = "") -> dict:
    """Validated write; returns a new table. Multi-select values are a list (deduplicated, order kept)."""
    f = FIELDS[name]
    vals = list(dict.fromkeys(value)) if f.multi else [value]
    bad = [v for v in vals if v not in f.values]
    if bad:
        raise ValueError(f"{name}: {bad} not in {f.values}")
    t = copy.deepcopy(table)
    t[name] = vals if f.multi else value
    if source or quote:
        t["bang_chung"].append({"truong": name, "gia_tri": t[name], "nguon": source, "trich": quote})
    return t


def scored_fields(table: dict) -> list[str]:
    """Fields that take part in scoring: filled and not in khong_chac."""
    return [n for n in FIELDS if is_filled(table, n) and n not in table.get("khong_chac", [])]
