"""One conversation, as a JSON-serialisable state dict (stored per session_id by the API, replayed by the simulator).

Flow (design doc 4 and 5.4): code fields come from the account lookup; the opening message (if any) is read without
counting as a question; then code picks a field, the model words the question, the answer fills the table (possibly
several fields), and code decides when to stop and what to conclude. A "don't know" still counts as one question.
"""
from __future__ import annotations

import time
from dataclasses import asdict

from . import dialog, vision
from .infer import MAX_QUESTIONS, choose_field, conclude, posterior, should_stop
from .scenarios import Scenario
from .lookup import ten_khop_tu_xung as name_match
from .schema import FIELDS, empty_table, set_value


def new_state(nhan_tai_khoan: str, loai_tai_khoan: str | None = None, ten_khop_tu_xung: str | None = None,
              so_tien: int | None = None, min_questions: int = 0) -> dict:
    """min_questions > 0: without an image, ask at least that many questions before concluding (E2 variant
    tinh_toan_min1; the app uses 0)."""
    t = set_value(empty_table(), "nhan_tai_khoan", nhan_tai_khoan, "tra_cuu", "nhãn tài khoản nhận")
    if loai_tai_khoan:
        t = set_value(t, "loai_tai_khoan", loai_tai_khoan, "tra_cuu", "loại tài khoản nhận")
    if ten_khop_tu_xung:
        t = set_value(t, "ten_khop_tu_xung", ten_khop_tu_xung, "tra_cuu", "so tên chủ tài khoản")
    return {"table": t, "asked": [], "pending": None, "history": [], "done": False, "conclusion": None,
            "so_tien": so_tien, "snapshots": [], "trace": [], "calls": [], "confirm_used": False,
            "min_questions": min_questions,
            "fill_log": [],  # per dien_bang call: source, fields kept, fills dropped for a quote not in the message
            # app: name match is worked out by code once tu_xung is known; the simulator passes it in directly
            "auto_ten_khop": ten_khop_tu_xung is None and loai_tai_khoan is not None}


def _log_call(state, kind, r):
    state["calls"].append({"kind": kind, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "seconds": r.seconds,
                           "usd": r.usd})


def apply_fills(state: dict, fills: list[dict], source: str) -> list[str]:
    changed = []
    for f in fills:
        state["table"] = set_value(state["table"], f["truong"], f["gia_tri"], source, f.get("trich", ""))
        changed.append(f["truong"])
    t = state["table"]
    if state.get("auto_ten_khop") and "tu_xung" in changed:
        m = name_match(t["loai_tai_khoan"], t["tu_xung"])
        if m:
            state["table"] = set_value(t, "ten_khop_tu_xung", m, "tra_cuu",
                                       f"tài khoản {t['loai_tai_khoan']}, người kia tự xưng {t['tu_xung']}")
    return changed


def _snapshot(state, scen):
    c = conclude(state["table"], scen, state["asked"])
    state["snapshots"].append({"n_asked": len(state["asked"]), "muc": c.muc, "top": c.top, "top_p": round(c.top_p, 4)})


CONFIRM = "__xac_nhan__"


def _next(state: dict, scen: dict[str, Scenario]) -> dict:
    """Ask the next question or conclude. Returns the assistant turn. An uncertain image reading gets one confirmation
    question per session, which does not count towards the 3 questions (design doc principle 4)."""
    post = posterior(state["table"], scen)
    top5 = dict(sorted(post.items(), key=lambda x: -x[1])[:5])
    if state.get("confirm") and not state["confirm_used"]:
        state["confirm_used"], state["pending"] = True, CONFIRM
        turn = {"role": "assistant", "text": state["confirm"], "kind": "xac_nhan",
                "phan_phoi": {k: round(v, 4) for k, v in top5.items()}}
        state["history"].append({"role": "assistant", "text": turn["text"]})
        return turn
    field = None
    must_ask = len(state["asked"]) < state.get("min_questions", 0) and not state.get("co_anh")
    if must_ask or not should_stop(post, len(state["asked"])):
        field, gains = choose_field(state["table"], state["asked"], scen, post)
    if field is None:
        c = conclude(state["table"], scen, state["asked"])
        r = dialog.viet_ket_luan(c, scen[c.top].ten, state["table"])
        _log_call(state, "ket_luan", r)
        state["done"], state["pending"] = True, None
        state["conclusion"] = {**asdict(c), "ten": scen[c.top].ten, "nhom": scen[c.top].nhom, "loi": r.text}
        turn = {"role": "assistant", "text": r.text, "kind": "ket_luan", "conclusion": state["conclusion"]}
    else:
        r = dialog.viet_cau_hoi(field, state["table"], state["history"], co_anh=state.get("co_anh", False))
        _log_call(state, "cau_hoi", r)
        state["asked"].append(field)
        state["pending"] = field
        turn = {"role": "assistant", "text": r.text, "kind": "cau_hoi", "truong": field}
        state["trace"].append({"truong": field, "phan_phoi": {k: round(v, 4) for k, v in top5.items()},
                               "loi_ich": {k: round(v, 3) for k, v in sorted(gains.items(), key=lambda x: -x[1])[:5]}})
    turn["phan_phoi"] = {k: round(v, 4) for k, v in top5.items()}
    state["history"].append({"role": "assistant", "text": turn["text"]})
    return turn


def _fill(state: dict, text: str, asked_field: str | None, source: str):
    fills, r, dropped = dialog.dien_bang(text, asked_field, state["history"][:-1])
    _log_call(state, "dien_bang", r)
    apply_fills(state, fills, source)
    state["fill_log"].append({"nguon": source, "dien": len(fills), "bo": dropped})


def start(state: dict, scen: dict[str, Scenario], opening: str | None = None) -> dict:
    """Read the opening message (0 questions), record the 0-question snapshot, then ask or conclude."""
    t0 = time.perf_counter()
    if opening:
        state["history"].append({"role": "user", "text": opening})
        _fill(state, opening, None, "tin_mo_dau")
    _snapshot(state, scen)
    turn = _next(state, scen)
    turn["seconds"] = round(time.perf_counter() - t0, 3)
    return turn


def add_image(state: dict, image: bytes) -> dict:
    """Read a chat screenshot into the table. Values the user already told us win; if the image says otherwise,
    mau_thuan_loi_ke_va_anh = co. An account in the image one character off the account being paid goes to khong_chac
    (an E1 finding: that is usually a misread, not a contradiction) and triggers the one confirmation question."""
    fields, strings, unsure, results = vision.read_image(image)
    for r in results:
        _log_call(state, "doc_anh", r)
    state["co_anh"] = True
    t = state["table"]
    conflicts, compared = [], False
    for n, v in fields.items():
        if FIELDS[n].multi:
            v = sorted(set(t[n]) | set(v)) if t[n] else v  # lists: what the user said plus what the image shows
            state["table"] = t = set_value(t, n, v, "anh", "đọc từ ảnh")
        elif t[n] is None:
            state["table"] = t = set_value(t, n, v, "anh", "đọc từ ảnh")
        else:
            compared = True
            if t[n] != v:
                conflicts.append(f"{n}: lời kể {t[n]}, ảnh {v}")
    for k, vals in strings.items():
        t["chuoi_trich"][k] = sorted(set(t["chuoi_trich"][k]) | set(vals))
    t["khong_chac"] = sorted(set(t["khong_chac"]) | set(unsure))
    paying = state.get("so_tk")
    accs = strings["account"]
    if paying and accs and paying not in accs:
        near = [a for a in accs if vision.one_char_off(a, paying)]
        if near:
            t["khong_chac"] = sorted(set(t["khong_chac"]) | {"chuoi:account"})
            state["confirm"] = (f"Số tài khoản trong ảnh mình đọc là {near[0]}, lệch một ký tự so với số bạn đang nhập "
                                f"({paying}). Bạn xem lại giúp số nào đúng nhé?")
        else:
            conflicts.append(f"số tài khoản: đang chuyển {paying}, ảnh có {', '.join(accs)}")
    elif paying and paying in accs:
        compared = True
    if conflicts or (compared and t["mau_thuan_loi_ke_va_anh"] != "co"):  # a contradiction seen once stays
        state["table"] = set_value(t, "mau_thuan_loi_ke_va_anh", "co" if conflicts else "khong", "so_sanh_anh",
                                   "; ".join(conflicts) or "ảnh khớp lời kể và số tài khoản")
    return {"truong": sorted(fields), "chuoi": strings, "khong_chac": state["table"]["khong_chac"], "mau_thuan": conflicts}


def answer(state: dict, scen: dict[str, Scenario], text: str, image: bytes | None = None) -> dict:
    """One user answer (text and/or image): fill, snapshot (k = questions asked so far), then ask or conclude.
    The answer to the confirmation question resolves the uncertain account and costs no question."""
    if state["done"]:
        raise ValueError("session already concluded")
    t0 = time.perf_counter()
    image_info = add_image(state, image) if image else None
    state["history"].append({"role": "user", "text": (text + " [ảnh]" if image else text).strip()})
    if state["pending"] == CONFIRM:
        state["table"]["khong_chac"] = [k for k in state["table"]["khong_chac"] if k != "chuoi:account"]
        state["confirm"] = None
    if text.strip():
        _fill(state, text, None if state["pending"] == CONFIRM else state["pending"], "tra_loi")
    _snapshot(state, scen)
    turn = _next(state, scen)
    turn["seconds"] = round(time.perf_counter() - t0, 3)
    if image_info:
        turn["doc_anh"] = image_info
    return turn


def field_label(name: str) -> str:
    return FIELDS[name].label


__all__ = ["new_state", "start", "answer", "apply_fills", "MAX_QUESTIONS"]
