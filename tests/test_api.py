"""API flow with the model stubbed: transfer check, session, decision -> report -> label loop, clusters."""
import importlib

import pytest
from fastapi.testclient import TestClient

from core import dialog, llm


def fake(text="", output=None):
    return llm.Result(output, text, 1, 1, 0.0, 0.0, "stub")


SHIP = [{"truong": "tu_xung", "gia_tri": ["shipper"], "trich": "shipper"},
        {"truong": "nguoi_lien_lac", "gia_tri": ["nguoi_la"], "trich": "lạ"},
        {"truong": "ai_bat_dau", "gia_tri": ["ho_truoc"], "trich": "nhắn trước"},
        {"truong": "ly_do_tien", "gia_tri": ["tra_hang"], "trich": "tiền hàng"}]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(dialog, "dien_bang",
                        lambda text, f, h: (dialog.clean_fills(SHIP if "shipper" in text else []), fake(), 0))
    monkeypatch.setattr(dialog, "viet_cau_hoi", lambda f, t, h, co_anh=False: fake(f"hỏi {f}?"))
    monkeypatch.setattr(dialog, "viet_ket_luan", lambda c, ten, table: fake(f"kết luận {c.muc}"))
    import app.db
    import app.main
    importlib.reload(app.db)
    importlib.reload(app.main)
    return TestClient(app.main.app)


def test_transfer_check_by_label(client):
    r = {n: client.post("/transfer/check", json={"so_tk": n, "so_tien": 1000}).json()
         for n in ("000123450001", "000123450004", "000123450007", "000123450010", "999 888 777")}
    assert r["000123450001"]["tro_chuyen"] == "khong"
    assert r["000123450004"]["tro_chuyen"] == "moi_kiem_tra" and r["000123450004"]["loi_moi"]
    assert (r["000123450007"]["canh_bao"], r["000123450007"]["tro_chuyen"]) == ("vang", "bat_luon")
    assert (r["000123450010"]["canh_bao"], r["000123450010"]["tro_chuyen"]) == ("do", "bat_luon")
    assert r["999 888 777"]["so_tk"] == "999888777" and r["999 888 777"]["nhan"] == "moi"


def test_report_turns_label_and_staff_confirms_and_removes(client):
    acc = "000123450004"  # moi, ca_nhan
    s = client.post("/sessions", json={"so_tk": acc, "so_tien": 30000}).json()
    assert s["kind"] == "cau_hoi" and s["vi_sao"]["truong"] and s["phan_phoi"]
    assert client.post(f"/sessions/{s['session_id']}/decision", json={"nut": "dung_lai"}).status_code == 409
    t = client.post(f"/sessions/{s['session_id']}/messages", data={"text": "shipper lạ nhắn trước đòi tiền hàng"}).json()
    assert t["done"] and t["ket_luan"]["muc"] == "giong_chieu_lua" and t["ket_luan"]["top"] == "gia_shipper"
    d = client.post(f"/sessions/{s['session_id']}/decision", json={"nut": "kiem_tra_them"}).json()
    assert d["nhan_tai_khoan"] == "dang_bi_bao_cao"
    assert client.post("/transfer/check", json={"so_tk": acc, "so_tien": 1}).json()["canh_bao"] == "vang"
    cl = client.get("/staff/clusters").json()
    assert cl["cum"][0]["tai_khoan"][0]["so_tk"] == acc and cl["cum"][0]["giong_chieu_lua"] == 1
    rep = client.get(f"/staff/reports/{d['report_id']}").json()
    assert rep["nut"] == "kiem_tra_them" and rep["noi_dung"]["bang_cau_chuyen"]["ten_khop_tu_xung"] == "khong"
    assert client.post(f"/staff/accounts/{acc}/label", json={"hanh_dong": "duyet"}).json()["nhan"] == "da_xac_nhan"
    assert client.post("/transfer/check", json={"so_tk": acc, "so_tien": 1}).json()["canh_bao"] == "do"
    assert client.post(f"/staff/accounts/{acc}/label", json={"hanh_dong": "go"}).json()["nhan"] == "moi"


def test_not_enough_goes_to_new_trick_list(client):
    s = client.post("/sessions", json={"so_tk": "000123450006", "so_tien": 5000}).json()
    for _ in range(3):
        t = client.post(f"/sessions/{s['session_id']}/messages", data={"text": "không biết"}).json()
    assert t["done"] and t["ket_luan"]["muc"] == "chua_du_can_cu"
    client.post(f"/sessions/{s['session_id']}/decision", json={"nut": "van_chuyen"})
    cl = client.get("/staff/clusters").json()
    assert cl["cum"] == [] and len(cl["co_the_la_chieu_moi"]) == 1
    assert client.post("/transfer/check", json={"so_tk": "000123450006", "so_tien": 1}).json()["nhan"] == "moi"


def test_image_one_char_off_gets_free_confirmation(client, monkeypatch):
    from core import vision
    rd = vision.Reading("vlm", {"kenh": "zalo", "tu_xung": "shipper"}, result=fake())
    rd.strings["account"] = ["000123450005"]  # paying 000123450004
    monkeypatch.setattr(vision, "READERS", [lambda img, model=None: rd])
    s = client.post("/sessions", json={"so_tk": "000123450004", "so_tien": 30000}).json()
    t = client.post(f"/sessions/{s['session_id']}/messages", files={"image": ("a.png", b"x", "image/png")}).json()
    assert t["kind"] == "xac_nhan" and "000123450005" in t["text"] and t["so_cau_da_hoi"] == s["so_cau_da_hoi"]
    assert t["doc_anh"]["khong_chac"] == ["chuoi:account"] and set(t["doc_anh"]["truong"]) == {"kenh", "tu_xung"}
    t = client.post(f"/sessions/{s['session_id']}/messages", data={"text": "đúng số 0004"}).json()
    assert t["kind"] in ("cau_hoi", "ket_luan")
