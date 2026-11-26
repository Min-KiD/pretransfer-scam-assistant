import math
import textwrap

import pytest

from core import infer
from core.scenarios import Scenario, load
from core.schema import empty_table, set_value


def scen(sid, nhom, truong, **kw):
    return Scenario(id=sid, ten=sid, nhom=nhom, mo_ta="", truong=truong, dau_hieu=[f"dh {sid}"],
                    viec_can_kiem_tra=[f"kt {sid}"], **kw)


@pytest.fixture
def two():
    return {"a": scen("a", "lua_dao", {"tu_xung": {"shipper": 0.9}, "ap_luc": {"hoi_thuc": 0.8}}),
            "b": scen("b", "binh_thuong", {"tu_xung": {"nguoi_ban": 0.9}, "ap_luc": {"khong_co": 0.9}})}


def test_single_unlisted_share_and_floor(two):
    d = infer.single_dist(two["a"], "tu_xung")
    assert d["shipper"] == 0.9
    # 0.1 left over 11 other values (incl. khac) is below the floor
    assert d["cong_an"] == infer.FLOOR and d["khac"] == infer.FLOOR
    s = scen("s", "lua_dao", {"ai_bat_dau": {"ho_truoc": 0.5}})
    assert infer.single_dist(s, "ai_bat_dau")["minh_truoc"] == pytest.approx(0.25)


def test_multi_select_is_yes_no_per_value(two):
    ll = infer.log_lik(two["a"], "ap_luc", ["hoi_thuc"])
    # present: hoi_thuc 0.8; absent: doa, hua_loi, giu_bi_mat, khong_co, khac at 1 - 0.02 each
    assert ll == pytest.approx(math.log(0.8) + 5 * math.log(0.98))


def test_posterior_uniform_prior_and_update(two):
    t = empty_table()
    assert infer.posterior(t, two) == pytest.approx({"a": 0.5, "b": 0.5})
    p = infer.posterior(set_value(t, "tu_xung", "shipper"), two)
    assert p["a"] == pytest.approx(0.9 / (0.9 + 0.02))


def test_khong_chac_field_is_ignored(two):
    t = set_value(empty_table(), "tu_xung", "shipper")
    t["khong_chac"] = ["tu_xung"]
    assert infer.posterior(t, two) == pytest.approx({"a": 0.5, "b": 0.5})


def test_choose_field_never_code_filled_or_asked(two):
    t = empty_table()
    f, gains = infer.choose_field(t, ["ap_luc"], two)
    assert f == "tu_xung"
    assert "ap_luc" not in gains and "loai_tai_khoan" not in gains and "nhan_tai_khoan" not in gains


def test_tie_prefers_image_checkable():
    # nguoi_lien_lac (not image-checkable) separates the scenarios slightly better than kenh (image-checkable);
    # the gap is under 10%, so kenh wins
    sc = {"a": scen("a", "lua_dao", {"nguoi_lien_lac": {"nguoi_la": 0.95}, "kenh": {"sms": 0.9}}),
          "b": scen("b", "binh_thuong", {"nguoi_lien_lac": {"nguoi_quen": 0.95}, "kenh": {"zalo": 0.9}})}
    f, gains = infer.choose_field(empty_table(), [], sc)
    assert gains["kenh"] < gains["nguoi_lien_lac"] < gains["kenh"] / 0.9
    assert f == "kenh"
    # a clear winner (gap over 10%) is kept even if it cannot be checked from an image
    sc["a"].truong["kenh"] = {"sms": 0.6}
    sc["b"].truong["kenh"] = {"zalo": 0.6}
    assert infer.choose_field(empty_table(), [], sc)[0] == "nguoi_lien_lac"


def test_stop_and_levels(two):
    t = set_value(empty_table(), "tu_xung", "shipper")
    post = infer.posterior(t, two)
    assert infer.should_stop(post, 0)
    c = infer.conclude(t, two)
    assert c.muc == "giong_chieu_lua" and c.top == "a" and c.dau_hieu == ["dh a"] and c.viec_can_kiem_tra == ["kt a"]
    assert c.can_cu[0]["truong"] == "tu_xung"
    assert not infer.should_stop({"a": 0.6, "b": 0.4}, 2) and infer.should_stop({"a": 0.6, "b": 0.4}, 3)
    t2 = set_value(empty_table(), "tu_xung", "nguoi_ban")
    assert infer.conclude(t2, two).muc == "giong_binh_thuong"


def test_below_half_is_not_enough(two):
    three = dict(two, c=scen("c", "lua_dao", {}))
    c = infer.conclude(empty_table(), three)
    assert c.muc == "chua_du_can_cu" and c.dau_hieu == [] and c.thieu


def write(d, name, body):
    (d / name).write_text(textwrap.dedent(body), encoding="utf-8")


BASE = """\
    id: {id}
    ten: x
    nhom: {nhom}
    mo_ta: x
    truong:
      tu_xung: {{shipper: 0.9}}
    dau_hieu: [x]
    viec_can_kiem_tra: [x]
"""


def test_loader_reports_file_and_line(tmp_path):
    write(tmp_path, "ok.yaml", BASE.format(id="ok", nhom="lua_dao"))
    write(tmp_path, "dup.yaml", BASE.format(id="ok", nhom="lua_dao"))
    write(tmp_path, "badval.yaml", BASE.format(id="bv", nhom="lua_dao").replace("shipper: 0.9", "phi_cong: 0.9"))
    write(tmp_path, "sum.yaml", BASE.format(id="sm", nhom="lua_dao").replace("{shipper: 0.9}",
                                                                              "{shipper: 0.9, cong_an: 0.3}"))
    write(tmp_path, "prob.yaml", BASE.format(id="pr", nhom="lua_dao").replace("0.9", "1.5"))
    write(tmp_path, "grp.yaml", BASE.format(id="gr", nhom="khac"))
    write(tmp_path, "ref.yaml", BASE.format(id="rf", nhom="binh_thuong") + "    kho_phan_biet_voi: khong_co_id\n")
    write(tmp_path, "syntax.yaml", "id: x\nmo_ta: a: b\n")
    sc, issues = load(tmp_path)
    assert set(sc) == {"ok"}
    msgs = {}
    for i in issues:
        msgs.setdefault(i.file.split("/")[-1], []).append((i.line, i.msg))
    msgs = {k: (v[0][0], " | ".join(m for _, m in v)) for k, v in msgs.items()}
    assert "trùng" in (msgs.get("dup.yaml") or msgs["ok.yaml"])[1]
    assert msgs["badval.yaml"] == (6, msgs["badval.yaml"][1]) and "phi_cong" in msgs["badval.yaml"][1]
    assert "tổng" in msgs["sum.yaml"][1]
    assert "ngoài (0, 1]" in msgs["prob.yaml"][1]
    assert "nhom" in msgs["grp.yaml"][1]
    assert "kho_phan_biet_voi" in msgs["ref.yaml"][1]
    assert msgs["syntax.yaml"][0] == 2


def test_real_library_loads():
    sc, _ = load()
    assert len(sc) >= 10
    assert {s.nhom for s in sc.values()} == {"lua_dao", "binh_thuong"}


def test_generated_cases_follow_v2_rules():
    """Ordinary stories carry no scam-type detail and never a confirmed-scam or known account; every label opens the
    chat. The detail list is the one the M3 training filter uses. T4b: a listed field only takes listed values, and
    every scenario has purpose lines, one of which the case carries."""
    import random

    from core.schema import FIELDS
    from sim.cases import ACCOUNT_LABEL, VIEC, make_case, scam_details
    sc, _ = load()
    assert set(VIEC) == set(sc), set(VIEC) ^ set(sc)
    assert all(VIEC[sid] and all(isinstance(v, str) and v.strip() for v in VIEC[sid]) for sid in sc)
    rng = random.Random(1)
    for sid, s in sc.items():
        for i in range(40):
            c = make_case(sid, i, sc, rng)
            t = c["bang_that"]
            assert c["viec"] in VIEC[sid]
            assert t["nhan_tai_khoan"] in ACCOUNT_LABEL[s.nhom]
            for name, listed in s.truong.items():
                if name == "nhan_tai_khoan":
                    continue
                got = t[name] if FIELDS[name].multi else [t[name]]
                assert set(got) <= set(listed), (sid, name, got)
            if s.nhom == "binh_thuong":
                assert not scam_details(t), (sid, scam_details(t))
    assert scam_details({"yeu_cau": ["chuyen_tien", "doc_otp"], "ly_do_tien": "tien_vay_chuyen_di", "ap_luc": ["doa"],
                         "duoc_dan_cach_tra_loi": "co"}) == ["yeu_cau=doc_otp", "ly_do_tien=tien_vay_chuyen_di",
                                                             "duoc_dan_cach_tra_loi=co", "ap_luc=doa"]
    assert set(ACCOUNT_LABEL["binh_thuong"]) == {"moi", "dang_bi_bao_cao"}
