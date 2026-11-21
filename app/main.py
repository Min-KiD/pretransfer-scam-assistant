"""FastAPI backend: the 7 endpoints of design doc section 8, plus the static web pages.

    uvicorn app.main:app   (or ./run_app.sh)
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import session as S
from core.lookup import CHAT, WARNING, normalise_account
from core.scenarios import load
from core.schema import FIELDS

from .db import DB

app = FastAPI(title="Trợ lý hỏi lại trước khi chuyển tiền")
SCEN, SCEN_ISSUES = load()
db = DB()
WEB = Path(__file__).resolve().parent.parent / "web"


def scen_names() -> dict:
    return {k: v.ten for k, v in SCEN.items()}


class TransferIn(BaseModel):
    so_tk: str
    so_tien: int


@app.post("/transfer/check")
def transfer_check(body: TransferIn):
    so_tk = normalise_account(body.so_tk)
    if not so_tk:
        raise HTTPException(400, "số tài khoản trống")
    acc = db.account(so_tk) or {"so_tk": so_tk, "ngan_hang": None, "chu_tk": None, "loai": None, "nhan": "moi"}
    return {"so_tk": so_tk, "ngan_hang": acc["ngan_hang"], "chu_tk": acc["chu_tk"], "loai": acc["loai"],
            "nhan": acc["nhan"], "canh_bao": WARNING[acc["nhan"]], "tro_chuyen": CHAT[acc["nhan"]],
            "loi_moi": "Lần đầu chuyển cho người này. Kiểm tra nhanh 30 giây?" if acc["nhan"] == "moi" else None}


class SessionIn(BaseModel):
    so_tk: str
    so_tien: int
    tin_mo_dau: str | None = None


def _turn_out(sid: str, turn: dict, state: dict) -> dict:
    out = {"session_id": sid, "text": turn["text"], "kind": turn["kind"], "done": state["done"],
           "so_cau_da_hoi": len(state["asked"]), "phan_phoi": turn.get("phan_phoi", {}), "ten_kich_ban": scen_names()}
    if turn["kind"] == "cau_hoi":
        tr = state["trace"][-1]
        out["vi_sao"] = {"truong": turn["truong"], "y_nghia": FIELDS[turn["truong"]].label, "loi_ich": tr["loi_ich"]}
    elif turn["kind"] == "xac_nhan":
        out["vi_sao"] = {"truong": "xac_nhan_so_tai_khoan", "y_nghia": "Ảnh và số đang nhập lệch một ký tự; câu xác "
                         "nhận này không tính vào 3 câu hỏi", "loi_ich": {}}
    else:
        c = state["conclusion"]
        out["ket_luan"] = {k: c[k] for k in ("muc", "top", "ten", "nhom", "top_p", "dau_hieu", "viec_can_kiem_tra",
                                             "can_cu", "thieu")}
    if "doc_anh" in turn:
        out["doc_anh"] = turn["doc_anh"]
    return out


@app.post("/sessions")
def create_session(body: SessionIn):
    so_tk = normalise_account(body.so_tk)
    acc = db.account(so_tk) or {"nhan": "moi", "loai": None}
    state = S.new_state(acc["nhan"], acc["loai"], None, body.so_tien)
    state["so_tk"] = so_tk
    sid = uuid.uuid4().hex[:12]
    if body.tin_mo_dau:
        db.add_message(sid, "user", body.tin_mo_dau)
    turn = S.start(state, SCEN, body.tin_mo_dau)
    db.add_message(sid, "assistant", turn["text"])
    db.save_session(sid, so_tk, body.so_tien, state)
    return _turn_out(sid, turn, state)


@app.post("/sessions/{sid}/messages")
async def post_message(sid: str, text: str = Form(""), image: UploadFile | None = File(None)):
    row = db.session(sid)
    if not row:
        raise HTTPException(404, "không có phiên này")
    state = row["state"]
    if state["done"]:
        raise HTTPException(409, "phiên đã kết luận")
    data = await image.read() if image is not None else None
    if not text.strip() and not data:
        raise HTTPException(400, "cần chữ hoặc ảnh")
    if data and len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "ảnh quá 8 MB")
    db.add_message(sid, "user", (text + " [ảnh]" if data else text).strip())
    turn = S.answer(state, SCEN, text, image=data)
    db.add_message(sid, "assistant", turn["text"])
    db.save_session(sid, row["so_tk"], row["so_tien"], state)
    return _turn_out(sid, turn, state)


class DecisionIn(BaseModel):
    nut: Literal["dung_lai", "kiem_tra_them", "van_chuyen"]


@app.post("/sessions/{sid}/decision")
def decision(sid: str, body: DecisionIn):
    row = db.session(sid)
    if not row:
        raise HTTPException(404, "không có phiên này")
    state = row["state"]
    if not state["done"]:
        raise HTTPException(409, "phiên chưa kết luận")
    c = state["conclusion"]
    content = {"bang_cau_chuyen": state["table"], "phan_phoi": c["phan_phoi"], "ket_luan": c,
               "cau_da_hoi": state["asked"], "hoi_thoai": db.messages(sid), "so_tien": row["so_tien"]}
    strings = state["table"]["chuoi_trich"]
    rid = db.add_report(sid, row["so_tk"], c["muc"], c["top"], body.nut, sorted(set(strings["phone"])),
                        sorted(set(strings["link"])), content)
    acc = db.account(row["so_tk"])
    if c["muc"] == "giong_chieu_lua" and (not acc or acc["nhan"] != "da_xac_nhan"):
        db.set_label(row["so_tk"], "dang_bi_bao_cao", "bao_cao_tu_dong")
    return {"report_id": rid, "nhan_tai_khoan": db.account(row["so_tk"])["nhan"]}


@app.get("/staff/clusters")
def clusters():
    """Reports joined when they share the receiving account, a phone number or a link. Reports that ended in
    'chưa đủ căn cứ' are listed apart as possible new tricks."""
    reps = db.reports()
    parent = {r["id"]: r["id"] for r in reps}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner = {}
    for r in reps:
        for key in [("tk", r["so_tk"])] + [("sdt", p) for p in r["sdt"]] + [("link", l) for l in r["link"]]:
            if key in owner:
                parent[find(r["id"])] = find(owner[key])
            else:
                owner[key] = r["id"]
    groups = {}
    for r in reps:
        groups.setdefault(find(r["id"]), []).append(r)
    out = []
    for rs in groups.values():
        accs = sorted({r["so_tk"] for r in rs})
        out.append({"tai_khoan": [{"so_tk": a, "nhan": (db.account(a) or {"nhan": "moi"})["nhan"],
                                   "chu_tk": (db.account(a) or {}).get("chu_tk")} for a in accs],
                    "sdt": sorted({p for r in rs for p in r["sdt"]}), "link": sorted({l for r in rs for l in r["link"]}),
                    "bao_cao": [{"id": r["id"], "muc": r["muc"], "kich_ban": SCEN[r["kich_ban"]].ten if r["kich_ban"] in SCEN
                                 else r["kich_ban"], "nut": r["nut"], "tao_luc": r["tao_luc"]} for r in rs],
                    "so_bao_cao": len(rs), "giong_chieu_lua": sum(r["muc"] == "giong_chieu_lua" for r in rs)})
    out.sort(key=lambda g: (-g["giong_chieu_lua"], -g["so_bao_cao"]))
    new = [{"id": r["id"], "so_tk": r["so_tk"], "tao_luc": r["tao_luc"]} for r in reps if r["muc"] == "chua_du_can_cu"]
    return {"cum": [g for g in out if g["giong_chieu_lua"] or not all(b["muc"] == "chua_du_can_cu" for b in g["bao_cao"])],
            "co_the_la_chieu_moi": new}


@app.get("/staff/reports/{rid}")
def report(rid: int):
    r = next((x for x in db.reports() if x["id"] == rid), None)
    if not r:
        raise HTTPException(404, "không có báo cáo này")
    r["tai_khoan"] = db.account(r["so_tk"])
    r["ten_kich_ban"] = scen_names()
    return r


class LabelIn(BaseModel):
    hanh_dong: Literal["duyet", "go"]


@app.post("/staff/accounts/{so_tk}/label")
def set_label(so_tk: str, body: LabelIn):
    so_tk = normalise_account(so_tk)
    if body.hanh_dong == "duyet":
        db.set_label(so_tk, "da_xac_nhan", "nhan_vien")
    else:  # "không phải lừa đảo": back to an unlabelled receiver
        db.set_label(so_tk, "moi", "nhan_vien_go")
    return db.account(so_tk)


@app.get("/")
def index():
    return RedirectResponse("/web/index.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")
