"""Self-contained unit & integration tests inside `e7/`."""
from __future__ import annotations

import json

import numpy as np
import pytest

from e7.eval import _precision_at_k, _recall_at_fpr, run_single_seed
from e7.gen_graph import GenPreset, generate_dataset, save_dataset
from e7.graph_engine import (
    GraphRiskConfig,
    build_bipartite_graph,
    extract_clusters,
    extract_louvain_communities,
    hard_label_propagation,
    label_spreading,
    score_account_graph,
    typed_linbp,
)
from e7.models import wl_subtree_feature_dict


def test_four_account_shopee_hub_example():
    """Verify the 4-account Shopee hotline / hub cutoff & evidence trail example."""
    accounts = [
        {"so_tk": "000100000001", "loai": "ca_nhan"},  # A: Old Scammer (confirmed)
        {"so_tk": "000100000002", "loai": "ca_nhan"},  # B: New Scammer (1-hop via rare phone)
        {"so_tk": "000100000003", "loai": "to_chuc"},  # C: Honest Shop (shares shopee.vn hub)
        {"so_tk": "000100000004", "loai": "ca_nhan"},  # D: Random Person (isolated)
    ]
    reports = [
        {"id": 1, "so_tk": "000100000001", "tao_luc": 10.0, "sdt": ["0987654321"], "link": ["https://shopee.vn/item/1"], "muc": "giong_chieu_lua"},
        {"id": 2, "so_tk": "000100000002", "tao_luc": 12.0, "sdt": ["0987654321"], "link": [], "muc": "giong_chieu_lua"},
        {"id": 3, "so_tk": "000100000003", "tao_luc": 12.0, "sdt": [], "link": ["shopee.vn"], "muc": "giong_binh_thuong"},
        {"id": 4, "so_tk": "000100000004", "tao_luc": 12.0, "sdt": ["0911111111"], "link": [], "muc": "giong_binh_thuong"},
    ]
    for i in range(24):
        sid = f"000200000{i:03d}"
        accounts.append({"so_tk": sid, "loai": "to_chuc"})
        reports.append({"id": 10 + i, "so_tk": sid, "tao_luc": 11.0, "sdt": [], "link": ["www.shopee.vn/shop"], "muc": "giong_binh_thuong"})

    cfg = GraphRiskConfig(hub_degree_cap=20, ppr_alpha=0.70, flag_threshold=0.20)
    res = score_account_graph(accounts, reports, confirmed_scam_ids={"000100000001"}, config=cfg)

    assert ("domain", "shopee.vn") in {(h["entity_type"], h["value"]) for h in res.filtered_hubs}
    b = res.account_scores["000100000002"]
    assert b["score"] == pytest.approx(0.70, abs=1e-4)
    assert b["status"] == "can_nhan_vien_xem"
    assert len(b["evidence_paths"]) == 1 and b["evidence_paths"][0]["hops"] == 1
    assert "098***321" in b["evidence_paths"][0]["summary"]

    for safe_id in ("000100000003", "000100000004"):
        assert res.account_scores[safe_id]["score"] == 0.0
        assert res.account_scores[safe_id]["status"] == "chua_du_can_cu"


def test_ppr_decays_monotonically_with_hops():
    accounts = [{"so_tk": f"00010000000{i}"} for i in range(1, 5)]
    reports = [
        {"id": 1, "so_tk": "000100000001", "day": 1, "sdt": ["0980000001"], "link": []},
        {"id": 2, "so_tk": "000100000002", "day": 2, "sdt": ["0980000001", "0980000002"], "link": []},
        {"id": 3, "so_tk": "000100000003", "day": 3, "sdt": ["0980000002", "0980000003"], "link": []},
        {"id": 4, "so_tk": "000100000004", "day": 4, "sdt": ["0980000003"], "link": []},
    ]
    res = score_account_graph(accounts, reports, confirmed_scam_ids={"000100000001"},
                              config=GraphRiskConfig(ppr_alpha=0.70, time_decay_per_day=0.0))
    scores = [res.account_scores[f"00010000000{i}"]["score"] for i in range(1, 5)]
    assert scores[0] == 1.0 and scores[0] > scores[1] > scores[2] > scores[3] > 0.0


def test_temporal_cutoff_prevents_leakage():
    accounts = [{"so_tk": "000100000001"}, {"so_tk": "000100000002"}]
    reports = [
        {"id": 1, "so_tk": "000100000001", "day": 10, "sdt": ["0980000099"], "link": []},
        {"id": 2, "so_tk": "000100000002", "day": 60, "sdt": ["0980000099"], "link": []},
    ]
    past = score_account_graph(accounts, reports, confirmed_scam_ids={"000100000001"}, cutoff_ts=55.0)
    assert past.account_scores["000100000002"]["score"] == 0.0
    future = score_account_graph(accounts, reports, confirmed_scam_ids={"000100000001"}, cutoff_ts=65.0)
    assert future.account_scores["000100000002"]["score"] > 0.5


def test_solvers_and_wl_subtrees_and_end_to_end(tmp_path):
    accounts = [{"so_tk": f"00030000000{i}", "loai": "ca_nhan" if i <= 2 else "to_chuc"} for i in range(1, 5)]
    reports = [
        {"id": 1, "so_tk": "000300000001", "day": 5, "sdt": ["0981111111"], "link": ["bad.xyz"], "muc": "giong_chieu_lua"},
        {"id": 2, "so_tk": "000300000002", "day": 6, "sdt": ["0981111111"], "link": ["bad.xyz"], "muc": "giong_chieu_lua"},
        {"id": 3, "so_tk": "000300000003", "day": 7, "sdt": ["0902222222"], "link": [], "muc": "giong_binh_thuong"},
        {"id": 4, "so_tk": "000300000004", "day": 8, "sdt": ["0902222222"], "link": [], "muc": "giong_binh_thuong"},
    ]
    g = build_bipartite_graph(accounts, reports)
    pos, neg = [g.account_index["000300000001"]], [g.account_index["000300000004"]]
    assert hard_label_propagation(g.W, pos, neg)[g.account_index["000300000002"]] > 0.5
    assert label_spreading(g.W, pos, negative_idx=neg)[g.account_index["000300000002"]] > 0.5
    bp = typed_linbp(g.W_by_type, pos, negative_idx=neg)
    assert np.all(np.isfinite(bp)) and bp[g.account_index["000300000002"]] > bp[g.account_index["000300000004"]]

    cls = extract_clusters(g, remove_hubs=True)
    assert len(cls) == 2
    assert wl_subtree_feature_dict(cls[0], g) != wl_subtree_feature_dict(cls[1], g)

    small = GenPreset(name="tiny", n_accounts=450, scam_rate=0.08)
    m1 = save_dataset(generate_dataset(small, seed=99), tmp_path / "r1")
    m2 = save_dataset(generate_dataset(small, seed=99), tmp_path / "r2")
    assert json.loads(m1.read_text())["sha256"] == json.loads(m2.read_text())["sha256"]

    out = run_single_seed(small, seed=99)
    n_arms = {r["arm"]: r for r in out["node_metrics"]}
    c_arms = {r["arm"]: r for r in out["cluster_metrics"]}
    assert n_arms["g1b_ppr"]["honest_shop_fpr"] <= n_arms["g0b_union_find"]["honest_shop_fpr"]
    assert n_arms["g3_hybrid_cs"]["pr_auc"] > n_arms["g0a_lookup"]["pr_auc"]
    assert {"g4_naive_uf_count", "g4_hubcut_uf_ppr", "g4_louvain_max_ppr", "g4_louvain_wl"} <= set(c_arms)
    y_dummy = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    assert _precision_at_k(y_dummy, np.zeros(10), 2) == pytest.approx(0.20)
    assert _recall_at_fpr(y_dummy, np.array([1.0, 0.9] + [0.1] * 8), 0.01) == pytest.approx(1.0)
    assert len(extract_louvain_communities(g)) == 2


def test_staff_reviews_follow_calendar_delay_and_truth():
    preset = GenPreset(name="tiny_staff", n_accounts=450, scam_rate=0.08,
                       staff_capacity_per_day=2, staff_min_delay_days=2)
    data = generate_dataset(preset, seed=7)
    capacity = {c["day"]: c["capacity"] for c in data["staff_calendar"]}
    truth = {a["so_tk"]: a for a in data["accounts"]}
    scam_verdict_days: dict[str, list[int]] = {}
    for r in data["reports"]:
        if r["muc"] == "giong_chieu_lua":
            scam_verdict_days.setdefault(r["so_tk"], []).append(r["day"])

    reviews = [e for e in data["label_events"] if e["by"] == "nhan_vien"]
    assert {e["label"] for e in reviews} == {"da_xac_nhan", "verified_normal"}
    per_day: dict[int, int] = {}
    for e in reviews:
        per_day[e["day"]] = per_day.get(e["day"], 0) + 1
        assert e["day"] - e["flagged_day"] >= preset.staff_min_delay_days
        assert e["flagged_day"] in scam_verdict_days[e["so_tk"]]
        acc = truth[e["so_tk"]]
        is_scam_then = acc["gt_is_scam"] and e["day"] >= acc.get("gt_hijack_day", 0)
        assert e["label"] == ("da_xac_nhan" if is_scam_then else "verified_normal")
    assert all(n <= capacity[day] for day, n in per_day.items())
    assert any(c["capacity"] == 0 for c in data["staff_calendar"])

    assert [r["id"] for r in data["reports"]] == list(range(1, len(data["reports"]) + 1))
    assert all(a["tao_luc"] <= b["tao_luc"] for a, b in zip(data["reports"], data["reports"][1:]))
    assert all(r["day"] - 1 <= r["tao_luc"] < r["day"] for r in data["reports"])
