"""Image path with the reader stubbed: merge of sources, one-character account rule, contradictions, confirmation."""
import pytest

from core import dialog, llm, session, vision
from core.scenarios import load


def res():
    return llm.Result({}, "", 1, 1, 0.0, 0.0, "stub")


def reading(src="vlm", fields=None, account=(), link=()):
    r = vision.Reading(src, dict(fields or {}), result=res())
    r.strings["account"] = list(account)
    r.strings["link"] = list(link)
    return r


def test_domain_only():
    assert vision.domain("https://WWW.Giaohang-Nhanh.top/don/AbC12") == "giaohang-nhanh.top"


def test_one_char_off():
    assert vision.one_char_off("000123450007", "000123450001")
    assert vision.one_char_off("00012345007", "000123450007")  # one digit dropped
    assert not vision.one_char_off("000123450007", "000123450007")
    assert not vision.one_char_off("000123450007", "000123459901")


def test_second_reader_disagreement_goes_to_khong_chac():
    a = reading("vlm", {"tu_xung": "shipper", "kenh": "sms"}, account=["0001 2345 0007"])
    b = reading("ocr", {"tu_xung": "shipper", "kenh": "zalo"}, account=["000123450001"])
    fields, strings, unsure = vision.merge([a, b])
    assert fields == {"tu_xung": "shipper"}
    assert "kenh" in unsure and "chuoi:account" in unsure
    assert strings["account"] == ["000123450001", "000123450007"]


@pytest.fixture
def scen():
    return load()[0]


@pytest.fixture
def stub(monkeypatch):
    box = {}
    monkeypatch.setattr(vision, "READERS", [lambda img: box["reading"]])
    monkeypatch.setattr(dialog, "dien_bang", lambda t, f, h: ([], res(), 0))
    monkeypatch.setattr(dialog, "viet_cau_hoi", lambda f, t, h, co_anh=False: llm.Result(None, f"hỏi {f}?", 1, 1, 0, 0, "s"))
    monkeypatch.setattr(dialog, "viet_ket_luan", lambda c, ten, t: llm.Result(None, "kết luận", 1, 1, 0, 0, "s"))
    return box


def new(so_tk="000123450007"):
    s = session.new_state("dang_bi_bao_cao", "ca_nhan")
    s["so_tk"] = so_tk
    return s


def test_one_char_off_account_asks_once_without_using_a_question(stub, scen):
    stub["reading"] = reading(fields={"kenh": "sms"}, account=["000123450001"])
    s = new()
    session.start(s, scen)
    asked = len(s["asked"])
    turn = session.answer(s, scen, "", image=b"img")
    assert turn["kind"] == "xac_nhan" and "000123450001" in turn["text"]
    assert "chuoi:account" in s["table"]["khong_chac"] and s["table"]["mau_thuan_loi_ke_va_anh"] is None
    assert len(s["asked"]) == asked  # the image answered the pending question; the confirmation is free
    turn = session.answer(s, scen, "đúng là số 0007")
    assert turn["kind"] != "xac_nhan" and "chuoi:account" not in s["table"]["khong_chac"]
    assert len(s["asked"]) == asked + (turn["kind"] == "cau_hoi")


def test_story_and_image_disagree_sets_contradiction(stub, scen):
    stub["reading"] = reading(fields={"tu_xung": "cong_an"}, account=["000123450007"], link=["vneid-xacminh.top"])
    s = new()
    session.start(s, scen)
    s["table"]["tu_xung"] = "shipper"  # the user said shipper earlier
    session.answer(s, scen, "", image=b"img")
    t = s["table"]
    assert t["tu_xung"] == "shipper" and t["mau_thuan_loi_ke_va_anh"] == "co"
    assert t["chuoi_trich"]["link"] == ["vneid-xacminh.top"]


def test_matching_image_says_no_contradiction_and_stays_co_once_seen(stub, scen):
    stub["reading"] = reading(fields={"kenh": "zalo"}, account=["000123450007"])
    s = new()
    session.start(s, scen)
    session.answer(s, scen, "", image=b"img")
    assert s["table"]["mau_thuan_loi_ke_va_anh"] == "khong" and s["table"]["kenh"] == "zalo"
    if not s["done"]:
        stub["reading"] = reading(account=["999999999999"])
        session.answer(s, scen, "", image=b"img2")
        assert s["table"]["mau_thuan_loi_ke_va_anh"] == "co"
