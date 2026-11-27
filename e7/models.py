"""E7 Node-Level Risk Classifiers (G0 -> G3) & Subgraph/Cluster Graph Classifiers (G4).

All arms run cleanly on CPU with strict leakage prevention and PU-safe training:
- Node-level arms:
  * g0a_lookup          : Current DB lookup only
  * g0b_union_find      : Current /staff/clusters naive Union-Find (exposes Shopee hub explosion)
  * g0c_neighbor_count  : Raw 1-hop confirmed scam neighbor count (no hub filter)
  * g1a_weighted_lp     : Hub-penalized Hard-Clamp Label Propagation (Zhu et al., ICML 2003)
  * g1b_ppr             : Hub-penalized Fading-Ink Personalized PageRank (PU-native core method)
  * g2a_label_spreading : Hub-penalized Soft-Clamp Label Spreading (Zhou et al., NeurIPS 2003)
  * g2b_linbp           : Typed-Edge Linearized Belief Propagation (LinBP / ZooBP)
  * g3_tabular_only     : Ablation — Tier-2 report features ONLY (no graph at all)
  * g3_hybrid_cs        : Seed-free Ego-Graph + Tier-2 Report ML -> Correct & Smooth + Monotonic PPR Fusion
                          (avoids PU 1-seed-per-ring sign inversion!)
- Subgraph / Cluster Graph Classification arms (true Graph Classification on /staff/clusters):
  * g4_naive_uf_count   : Current /staff/clusters naive Union-Find ranked by scam report count
  * g4_hubcut_max_ppr   : Hub-filtered clusters ranked by max PPR node score
  * g4_cluster_wl       : 1-WL Weisfeiler-Lehman Subtree Kernel + FRAUDAR camouflage-resistant density
                          + temporal burstiness + scenario consensus -> classifier
"""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import sparse
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

from e7.graph_engine import (
    BipartiteGraph,
    GraphRiskConfig,
    build_bipartite_graph,
    extract_clusters,
    extract_louvain_communities,
    hard_label_propagation,
    label_spreading,
    personalized_pagerank,
    sym_normalise,
    typed_linbp,
)


@dataclass
class NodeArmOutput:
    name: str
    val_scores: dict[str, float]
    test_scores: dict[str, float]
    threshold: float
    best_params: dict[str, Any]
    fit_ms: float
    infer_ms: float
    abstain_mask_test: dict[str, bool]


@dataclass
class ClusterArmOutput:
    name: str
    val_clusters: list[dict[str, Any]]
    test_clusters: list[dict[str, Any]]
    val_scores: np.ndarray
    test_scores: np.ndarray
    threshold: float
    best_params: dict[str, Any]
    fit_ms: float
    infer_ms: float


def _pick_threshold(y_true: np.ndarray, scores: np.ndarray, target_fpr: float = 0.02) -> float:
    """Select decision threshold strictly on validation set maximizing F1 subject to FPR <= target_fpr."""
    if len(y_true) == 0 or np.sum(y_true) == 0:
        return 0.5
    uniq = np.unique(scores)
    if len(uniq) == 1:
        return float(uniq[0]) + 1e-6
    cands = np.unique(np.concatenate([
        np.quantile(scores, np.linspace(0.50, 0.995, 90)),
        uniq[uniq > 0][:30],
    ]))
    best_thr, best_f1 = float(np.quantile(scores, 0.95)), -1.0
    neg = (y_true == 0)
    pos = (y_true == 1)
    n_neg = max(int(np.sum(neg)), 1)
    n_pos = max(int(np.sum(pos)), 1)
    for thr in cands:
        pred = scores >= thr
        fp = int(np.sum(pred & neg))
        if fp / n_neg > target_fpr:
            continue
        tp = int(np.sum(pred & pos))
        if tp == 0:
            continue
        prec = tp / max(tp + fp, 1)
        rec = tp / n_pos
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        if f1 > best_f1:
            best_f1 = f1
            best_thr = float(thr)
    if best_f1 < 0:
        neg_scores = scores[neg]
        best_thr = float(np.quantile(neg_scores, 1.0 - target_fpr)) + 1e-6 if len(neg_scores) else 0.5
    return best_thr


def _ap_safe(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(y_true) == 0 or np.sum(y_true) == 0 or np.sum(y_true) == len(y_true):
        return 0.0
    return float(average_precision_score(y_true, scores))


def _seed_indices(graph: BipartiteGraph, ids: set[str]) -> list[int]:
    return [graph.account_index[s] for s in sorted(ids) if s in graph.account_index]


def _scores_to_dict(graph: BipartiteGraph, arr: np.ndarray, subset: list[str]) -> dict[str, float]:
    return {sid: float(arr[graph.account_index[sid]]) if sid in graph.account_index else 0.0 for sid in subset}


# ---------------------------------------------------------------------------
# G0 baselines (Lookup, Naive Union-Find, 1-hop Confirmed Neighbor Count)
# ---------------------------------------------------------------------------
def run_g0a_lookup(val_ids: list[str], test_ids: list[str], train_pos_seeds: set[str]) -> NodeArmOutput:
    t0 = time.perf_counter()
    val_sc = {s: (1.0 if s in train_pos_seeds else 0.0) for s in val_ids}
    test_sc = {s: (1.0 if s in train_pos_seeds else 0.0) for s in test_ids}
    dt = (time.perf_counter() - t0) * 1000.0
    return NodeArmOutput(
        name="g0a_lookup",
        val_scores=val_sc, test_scores=test_sc, threshold=0.5, best_params={},
        fit_ms=0.0, infer_ms=round(dt, 2),
        abstain_mask_test={s: s not in train_pos_seeds for s in test_ids},
    )


def run_g0b_union_find(
    val_graph: BipartiteGraph, test_graph: BipartiteGraph,
    val_ids: list[str], test_ids: list[str], train_pos_seeds: set[str],
) -> NodeArmOutput:
    """Reproduces naive /staff/clusters Union-Find WITHOUT hub filtering."""
    def _score_graph(g: BipartiteGraph, target_ids: list[str]) -> dict[str, float]:
        flagged: set[str] = set()
        for cl in extract_clusters(g, remove_hubs=False):
            if any(a in train_pos_seeds for a in cl["accounts"]):
                flagged.update(cl["accounts"])
        return {s: (1.0 if s in flagged else 0.0) for s in target_ids}

    t0 = time.perf_counter()
    val_sc = _score_graph(val_graph, val_ids)
    t1 = time.perf_counter()
    test_sc = _score_graph(test_graph, test_ids)
    t2 = time.perf_counter()
    return NodeArmOutput(
        name="g0b_union_find",
        val_scores=val_sc, test_scores=test_sc, threshold=0.5,
        best_params={"remove_hubs": False},
        fit_ms=round((t1 - t0) * 1000.0, 2), infer_ms=round((t2 - t1) * 1000.0, 2),
        abstain_mask_test={s: test_sc[s] == 0.0 for s in test_ids},
    )


def run_g0c_neighbor_count(
    val_graph: BipartiteGraph, test_graph: BipartiteGraph,
    val_ids: list[str], test_ids: list[str], y_val: np.ndarray, train_pos_seeds: set[str],
) -> NodeArmOutput:
    """1-hop confirmed scam neighbor count across ALL shared entities (no hub filtering)."""
    def _count(g: BipartiteGraph, target_ids: list[str]) -> dict[str, float]:
        out = {}
        for sid in target_ids:
            nbr_seeds = set()
            for ek in g.acc_to_ent_all.get(sid, {}):
                for other in g.ent_to_acc_all.get(ek, {}):
                    if other != sid and other in train_pos_seeds:
                        nbr_seeds.add(other)
            out[sid] = float(len(nbr_seeds))
        return out

    t0 = time.perf_counter()
    val_sc = _count(val_graph, val_ids)
    thr = _pick_threshold(y_val, np.array([val_sc[s] for s in val_ids]))
    t1 = time.perf_counter()
    test_sc = _count(test_graph, test_ids)
    t2 = time.perf_counter()
    return NodeArmOutput(
        name="g0c_neighbor_count",
        val_scores=val_sc, test_scores=test_sc, threshold=thr,
        best_params={"hub_filter": False},
        fit_ms=round((t1 - t0) * 1000.0, 2), infer_ms=round((t2 - t1) * 1000.0, 2),
        abstain_mask_test={s: test_sc[s] == 0.0 for s in test_ids},
    )


# ---------------------------------------------------------------------------
# G1 & G2 propagation arms (Weighted LP, PPR, Label Spreading, Typed LinBP)
# ---------------------------------------------------------------------------
def run_g1a_weighted_lp(
    accounts: list[dict[str, Any]], reports: list[dict[str, Any]],
    val_cutoff: float, test_cutoff: float,
    val_ids: list[str], test_ids: list[str], y_val: np.ndarray,
    train_pos_seeds: set[str], train_neg_seeds: set[str],
) -> NodeArmOutput:
    t0 = time.perf_counter()
    best = (-1.0, 20, {})
    for cap in (15, 25):
        vg = build_bipartite_graph(accounts, reports, cutoff_ts=val_cutoff, config=GraphRiskConfig(hub_degree_cap=cap))
        arr = hard_label_propagation(vg.W, _seed_indices(vg, train_pos_seeds), _seed_indices(vg, train_neg_seeds))
        vsc = _scores_to_dict(vg, arr, val_ids)
        ap = _ap_safe(y_val, np.array([vsc[s] for s in val_ids]))
        if ap > best[0]:
            best = (ap, cap, vsc)
    _, best_cap, val_sc = best
    thr = _pick_threshold(y_val, np.array([val_sc[s] for s in val_ids]))
    t1 = time.perf_counter()

    tg = build_bipartite_graph(accounts, reports, cutoff_ts=test_cutoff, config=GraphRiskConfig(hub_degree_cap=best_cap))
    t_arr = hard_label_propagation(tg.W, _seed_indices(tg, train_pos_seeds), _seed_indices(tg, train_neg_seeds))
    test_sc = _scores_to_dict(tg, t_arr, test_ids)
    t2 = time.perf_counter()

    deg_test = np.asarray(tg.W.sum(axis=1)).ravel()
    abstain = {
        s: (s not in tg.account_index or deg_test[tg.account_index[s]] == 0.0 or test_sc[s] == 0.5)
        for s in test_ids
    }
    return NodeArmOutput(
        name="g1a_weighted_lp",
        val_scores=val_sc, test_scores=test_sc, threshold=thr,
        best_params={"hub_degree_cap": best_cap, "has_neg_seeds": len(train_neg_seeds) > 0},
        fit_ms=round((t1 - t0) * 1000.0, 2), infer_ms=round((t2 - t1) * 1000.0, 2),
        abstain_mask_test=abstain,
    )


def run_g1b_ppr(
    accounts: list[dict[str, Any]], reports: list[dict[str, Any]],
    val_cutoff: float, test_cutoff: float,
    val_ids: list[str], test_ids: list[str], y_val: np.ndarray,
    train_pos_seeds: set[str],
) -> NodeArmOutput:
    t0 = time.perf_counter()
    best = (-1.0, 20, 0.70, 1.5, {})
    for cap in (12, 20, 30):
        for beta in (1.0, 1.5):
            vg = build_bipartite_graph(
                accounts, reports, cutoff_ts=val_cutoff,
                config=GraphRiskConfig(hub_degree_cap=cap, rarity_power=beta),
            )
            pidx = _seed_indices(vg, train_pos_seeds)
            for alpha in (0.55, 0.70, 0.85):
                arr = personalized_pagerank(vg.W, pidx, alpha=alpha)
                vsc = _scores_to_dict(vg, arr, val_ids)
                ap = _ap_safe(y_val, np.array([vsc[s] for s in val_ids]))
                if ap > best[0]:
                    best = (ap, cap, alpha, beta, vsc)
    _, best_cap, best_alpha, best_beta, val_sc = best
    thr = _pick_threshold(y_val, np.array([val_sc[s] for s in val_ids]))
    t1 = time.perf_counter()

    tg = build_bipartite_graph(
        accounts, reports, cutoff_ts=test_cutoff,
        config=GraphRiskConfig(hub_degree_cap=best_cap, rarity_power=best_beta, ppr_alpha=best_alpha),
    )
    t_arr = personalized_pagerank(tg.W, _seed_indices(tg, train_pos_seeds), alpha=best_alpha)
    test_sc = _scores_to_dict(tg, t_arr, test_ids)
    t2 = time.perf_counter()

    return NodeArmOutput(
        name="g1b_ppr",
        val_scores=val_sc, test_scores=test_sc, threshold=thr,
        best_params={"hub_degree_cap": best_cap, "alpha": best_alpha, "rarity_power": best_beta},
        fit_ms=round((t1 - t0) * 1000.0, 2), infer_ms=round((t2 - t1) * 1000.0, 2),
        abstain_mask_test={s: test_sc[s] < 1e-4 for s in test_ids},
    )


def run_g2a_label_spreading(
    accounts: list[dict[str, Any]], reports: list[dict[str, Any]],
    val_cutoff: float, test_cutoff: float,
    val_ids: list[str], test_ids: list[str], y_val: np.ndarray,
    train_pos_seeds: set[str], train_neg_seeds: set[str],
    val_weak_ids: set[str], test_weak_ids: set[str],
) -> NodeArmOutput:
    t0 = time.perf_counter()
    best = (-1.0, 20, 0.65, 0.0, {})
    for cap in (15, 25):
        vg = build_bipartite_graph(accounts, reports, cutoff_ts=val_cutoff, config=GraphRiskConfig(hub_degree_cap=cap))
        pidx = _seed_indices(vg, train_pos_seeds)
        nidx = _seed_indices(vg, train_neg_seeds)
        widx = _seed_indices(vg, val_weak_ids - train_pos_seeds - train_neg_seeds)
        for alpha in (0.50, 0.70):
            for ww in (0.0, 0.15, 0.30):
                arr = label_spreading(
                    vg.W, pidx, negative_idx=nidx or None,
                    weak_idx=widx or None, weak_weight=ww, alpha=alpha,
                )
                vsc = _scores_to_dict(vg, arr, val_ids)
                ap = _ap_safe(y_val, np.array([vsc[s] for s in val_ids]))
                if ap > best[0]:
                    best = (ap, cap, alpha, ww, vsc)
    _, best_cap, best_alpha, best_ww, val_sc = best
    thr = _pick_threshold(y_val, np.array([val_sc[s] for s in val_ids]))
    t1 = time.perf_counter()

    tg = build_bipartite_graph(accounts, reports, cutoff_ts=test_cutoff, config=GraphRiskConfig(hub_degree_cap=best_cap))
    t_arr = label_spreading(
        tg.W,
        _seed_indices(tg, train_pos_seeds),
        negative_idx=_seed_indices(tg, train_neg_seeds) or None,
        weak_idx=_seed_indices(tg, test_weak_ids - train_pos_seeds - train_neg_seeds) or None,
        weak_weight=best_ww,
        alpha=best_alpha,
    )
    test_sc = _scores_to_dict(tg, t_arr, test_ids)
    t2 = time.perf_counter()

    return NodeArmOutput(
        name="g2a_label_spreading",
        val_scores=val_sc, test_scores=test_sc, threshold=thr,
        best_params={"hub_degree_cap": best_cap, "alpha": best_alpha, "weak_weight": best_ww},
        fit_ms=round((t1 - t0) * 1000.0, 2), infer_ms=round((t2 - t1) * 1000.0, 2),
        abstain_mask_test={s: test_sc[s] < 1e-4 for s in test_ids},
    )


def run_g2b_linbp(
    accounts: list[dict[str, Any]], reports: list[dict[str, Any]],
    val_cutoff: float, test_cutoff: float,
    val_ids: list[str], test_ids: list[str], y_val: np.ndarray,
    train_pos_seeds: set[str], train_neg_seeds: set[str],
    val_weak_ids: set[str], test_weak_ids: set[str],
) -> NodeArmOutput:
    """Typed-Edge LinBP tuning per-relation signed compatibility weights h_r on validation."""
    t0 = time.perf_counter()
    h_grid = [
        {"phone_rare": 0.50, "phone_mid": 0.15, "domain_rare": 0.40, "domain_mid": 0.08},
        {"phone_rare": 0.55, "phone_mid": 0.05, "domain_rare": 0.45, "domain_mid": 0.02},
        {"phone_rare": 0.45, "phone_mid": 0.00, "domain_rare": 0.55, "domain_mid": 0.00},
        {"phone_rare": 0.35, "phone_mid": -0.05, "domain_rare": 0.50, "domain_mid": 0.00},
    ]
    best = (-1.0, 20, h_grid[0], 0.0, {})
    for cap in (15, 25):
        vg = build_bipartite_graph(accounts, reports, cutoff_ts=val_cutoff, config=GraphRiskConfig(hub_degree_cap=cap))
        pidx = _seed_indices(vg, train_pos_seeds)
        nidx = _seed_indices(vg, train_neg_seeds)
        widx = _seed_indices(vg, val_weak_ids - train_pos_seeds - train_neg_seeds)
        for h_map in h_grid:
            for wp in (0.0, 0.12):
                arr = typed_linbp(
                    vg.W_by_type, pidx, negative_idx=nidx or None,
                    weak_idx=widx or None, h_by_type=h_map, weak_prior=wp,
                )
                vsc = _scores_to_dict(vg, arr, val_ids)
                ap = _ap_safe(y_val, np.array([vsc[s] for s in val_ids]))
                if ap > best[0]:
                    best = (ap, cap, h_map, wp, vsc)
    _, best_cap, best_h, best_wp, val_sc = best
    thr = _pick_threshold(y_val, np.array([val_sc[s] for s in val_ids]))
    t1 = time.perf_counter()

    tg = build_bipartite_graph(accounts, reports, cutoff_ts=test_cutoff, config=GraphRiskConfig(hub_degree_cap=best_cap))
    t_arr = typed_linbp(
        tg.W_by_type,
        _seed_indices(tg, train_pos_seeds),
        negative_idx=_seed_indices(tg, train_neg_seeds) or None,
        weak_idx=_seed_indices(tg, test_weak_ids - train_pos_seeds - train_neg_seeds) or None,
        h_by_type=best_h,
        weak_prior=best_wp,
    )
    test_sc = _scores_to_dict(tg, t_arr, test_ids)
    t2 = time.perf_counter()

    return NodeArmOutput(
        name="g2b_linbp",
        val_scores=val_sc, test_scores=test_sc, threshold=thr,
        best_params={"hub_degree_cap": best_cap, "h_by_type": best_h, "weak_prior": best_wp},
        fit_ms=round((t1 - t0) * 1000.0, 2), infer_ms=round((t2 - t1) * 1000.0, 2),
        abstain_mask_test={s: test_sc[s] < 1e-4 for s in test_ids},
    )


# ---------------------------------------------------------------------------
# G3: Hybrid Seed-Free Ego-Graph + Tabular ML -> Correct & Smooth + Monotonic PPR Fusion
# ---------------------------------------------------------------------------
def _extract_account_tabular_features(
    graph: BipartiteGraph,
    scenario_ids: list[str],
    target_ids: list[str],
) -> np.ndarray:
    """Strictly observable own-account & Tier-2 report features (ZERO graph, ZERO ground truth)."""
    reps_by_acc: dict[str, list[dict[str, Any]]] = {s: [] for s in target_ids}
    target_set = set(target_ids)
    for r in graph.reports:
        sid = r["_so_tk"]
        if sid in target_set:
            reps_by_acc[sid].append(r)

    scen_idx = {sid: i for i, sid in enumerate(scenario_ids)}
    n_scen = len(scenario_ids)
    X = np.zeros((len(target_ids), 13 + n_scen), dtype=np.float64)

    for row_i, sid in enumerate(target_ids):
        meta = graph.account_meta.get(sid, {})
        reps = reps_by_acc[sid]
        n_rep = len(reps)

        X[row_i, 0] = 1.0 if meta.get("loai") == "ca_nhan" else 0.0
        X[row_i, 1] = 1.0 if meta.get("loai") == "to_chuc" else 0.0
        X[row_i, 2] = math.log1p(n_rep)

        if n_rep > 0:
            n_scam = sum(1 for r in reps if r.get("muc") == "giong_chieu_lua")
            n_unc = sum(1 for r in reps if r.get("muc") == "chua_du_can_cu")
            n_stop = sum(1 for r in reps if r.get("nut") == "dung_lai")
            n_check = sum(1 for r in reps if r.get("nut") == "kiem_tra_them")
            n_mismatch = sum(1 for r in reps if r.get("ten_khop_tu_xung") == "khong")
            m3_probs = [float(r.get("m3_scam_prob", 0.5)) for r in reps]
            amounts = [math.log1p(max(0.0, float(r.get("so_tien") or 0.0))) for r in reps]
            days = [float(r["_ts"]) for r in reps]
            span = max(days) - min(days) if len(days) > 1 else 0.0

            X[row_i, 3] = n_scam / n_rep
            X[row_i, 4] = n_unc / n_rep
            X[row_i, 5] = n_stop / n_rep
            X[row_i, 6] = n_check / n_rep
            X[row_i, 7] = n_mismatch / n_rep
            X[row_i, 8] = float(np.mean(m3_probs))
            X[row_i, 9] = float(np.max(m3_probs))
            X[row_i, 10] = float(np.mean(amounts))
            X[row_i, 11] = math.log1p(span)
            X[row_i, 12] = float(len({p for r in reps for p in r["_phones"]}) + len({d for r in reps for d in r["_domains"]}))

            for r in reps:
                for sc_id, p in (r.get("phan_phoi") or {}).items():
                    if sc_id in scen_idx:
                        X[row_i, 13 + scen_idx[sc_id]] += float(p) / n_rep
    return X


def _extract_seed_free_ego_features(
    graph: BipartiteGraph,
    target_ids: list[str],
) -> np.ndarray:
    """Hub-filtered ego-neighborhood features that depend ONLY on observable reports/topology
    (ZERO seed labels -> immune to PU 1-seed-per-ring sign inversion AND works on cold-start rings!)."""
    m3_by_acc: dict[str, list[float]] = {}
    scam_by_acc: dict[str, list[float]] = {}
    stop_by_acc: dict[str, list[float]] = {}
    for r in graph.reports:
        sid = r["_so_tk"]
        m3_by_acc.setdefault(sid, []).append(float(r.get("m3_scam_prob", 0.5)))
        scam_by_acc.setdefault(sid, []).append(1.0 if r.get("muc") == "giong_chieu_lua" else 0.0)
        stop_by_acc.setdefault(sid, []).append(1.0 if r.get("nut") == "dung_lai" else 0.0)

    acc_m3 = {s: float(np.mean(v)) for s, v in m3_by_acc.items()}
    acc_scam = {s: float(np.mean(v)) for s, v in scam_by_acc.items()}
    acc_stop = {s: float(np.mean(v)) for s, v in stop_by_acc.items()}

    cl_size: dict[str, int] = {}
    cl_scam_rate: dict[str, float] = {}
    for cl in extract_clusters(graph, remove_hubs=True):
        sz = len(cl["accounts"])
        sr = cl["n_scam_reports"] / max(cl["n_reports"], 1)
        for a in cl["accounts"]:
            cl_size[a] = sz
            cl_scam_rate[a] = sr

    row_sum_w = np.asarray(graph.W.sum(axis=1)).ravel()
    G = np.zeros((len(target_ids), 10), dtype=np.float64)

    for row_i, sid in enumerate(target_ids):
        if sid not in graph.account_index:
            continue
        idx = graph.account_index[sid]
        G[row_i, 0] = math.log1p(row_sum_w[idx])

        n_rare_ph, n_rare_dom = 0, 0
        max_inv_ld = 0.0
        w_m3, w_scam, w_stop, w_tot = 0.0, 0.0, 0.0, 0.0
        nbrs: set[str] = set()
        for ek in graph.acc_to_ent.get(sid, {}):
            deg = graph.entity_degree[ek]
            if deg < 2:
                continue
            ew = graph.entity_weights[ek]
            max_inv_ld = max(max_inv_ld, 1.0 / max(math.log(1.0 + deg), 1e-6))
            if ek[0] == "phone" and deg <= 6:
                n_rare_ph += 1
            elif ek[0] == "domain" and deg <= 8:
                n_rare_dom += 1
            for other in graph.ent_to_acc.get(ek, {}):
                if other == sid:
                    continue
                nbrs.add(other)
                if other in acc_m3:
                    w_m3 += ew * acc_m3[other]
                    w_scam += ew * acc_scam[other]
                    w_stop += ew * acc_stop[other]
                    w_tot += ew

        G[row_i, 1] = math.log1p(len(nbrs))
        G[row_i, 2] = float(n_rare_ph)
        G[row_i, 3] = float(n_rare_dom)
        G[row_i, 4] = max_inv_ld
        G[row_i, 5] = (w_m3 / w_tot) if w_tot > 0 else 0.0
        G[row_i, 6] = (w_scam / w_tot) if w_tot > 0 else 0.0
        G[row_i, 7] = (w_stop / w_tot) if w_tot > 0 else 0.0
        G[row_i, 8] = math.log1p(cl_size.get(sid, 1))
        G[row_i, 9] = cl_scam_rate.get(sid, 0.0)
    return G


def _correct_and_smooth(
    graph: BipartiteGraph,
    base_probs: dict[str, float],
    train_pos_seeds: set[str],
    train_neg_seeds: set[str],
    *,
    alpha1: float = 0.50,
    alpha2: float = 0.50,
    scale: float = 0.80,
    n_iter: int = 40,
) -> np.ndarray:
    """Correct & Smooth (Huang et al., ICLR 2021) on hub-filtered normalised S."""
    n = len(graph.account_ids)
    z = np.array([base_probs.get(s, 0.0) for s in graph.account_ids], dtype=np.float64)
    if graph.W.nnz == 0:
        return z
    S = sym_normalise(graph.W)
    pos_idx = _seed_indices(graph, train_pos_seeds)
    neg_idx = _seed_indices(graph, train_neg_seeds)

    err = np.zeros(n, dtype=np.float64)
    if pos_idx:
        err[pos_idx] = 1.0 - z[pos_idx]
    if neg_idx:
        err[neg_idx] = 0.0 - z[neg_idx]
    e_hat = err.copy()
    for _ in range(n_iter):
        e_hat = alpha1 * (S @ e_hat) + (1.0 - alpha1) * err
    z_corr = np.clip(z + scale * e_hat, 0.0, 1.0)

    g0 = z_corr.copy()
    if pos_idx:
        g0[pos_idx] = 1.0
    if neg_idx:
        g0[neg_idx] = 0.0
    y_hat = g0.copy()
    for _ in range(n_iter):
        y_hat = alpha2 * (S @ y_hat) + (1.0 - alpha2) * g0
    return np.clip(y_hat, 0.0, 1.0)


def _fit_pu_ensemble(
    X_tr: np.ndarray,
    y_tr_obs: np.ndarray,
    X_va: np.ndarray,
    y_va: np.ndarray,
) -> tuple[Any, dict[str, Any]]:
    """Train a PU-safe LogisticRegression + HistGradientBoosting ensemble tuned on validation AP."""
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)

    n_pos = int(np.sum(y_tr_obs == 1))
    best_lr = (-1.0, 1.0, None, None)
    for C in (0.1, 0.5, 2.0):
        lr = LogisticRegression(C=C, class_weight="balanced", max_iter=1500, random_state=42)
        lr.fit(X_tr_s, y_tr_obs)
        p_va = lr.predict_proba(X_va_s)[:, 1]
        ap = _ap_safe(y_va, p_va)
        if ap > best_lr[0]:
            best_lr = (ap, C, lr, p_va)
    lr_mod = best_lr[2]
    p_lr_va = best_lr[3]

    min_leaf = max(2, min(8, n_pos // 2))
    hgb = HistGradientBoostingClassifier(
        max_depth=3, max_iter=100, learning_rate=0.05, min_samples_leaf=min_leaf,
        l2_regularization=1.5, class_weight="balanced", random_state=42,
    )
    hgb.fit(X_tr, y_tr_obs)
    p_hgb_va = hgb.predict_proba(X_va)[:, 1]

    best_w = (-1.0, 1.0)
    for w_lr in (1.0, 0.75, 0.55, 0.35):
        ap = _ap_safe(y_va, w_lr * p_lr_va + (1.0 - w_lr) * p_hgb_va)
        if ap > best_w[0]:
            best_w = (ap, w_lr)
    w_lr = best_w[1]

    def predict(X_new: np.ndarray) -> np.ndarray:
        p1 = lr_mod.predict_proba(scaler.transform(X_new))[:, 1]
        if w_lr >= 0.999:
            return p1
        return w_lr * p1 + (1.0 - w_lr) * hgb.predict_proba(X_new)[:, 1]

    return predict, {"C": best_lr[1], "w_lr": w_lr, "min_leaf": min_leaf}


def run_g3_hybrid_arms(
    accounts: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    scenario_ids: list[str],
    train_cutoff: float,
    val_cutoff: float,
    test_cutoff: float,
    train_ids: list[str],
    val_ids: list[str],
    test_ids: list[str],
    y_val: np.ndarray,
    train_pos_seeds: set[str],
    train_neg_seeds: set[str],
) -> tuple[NodeArmOutput, NodeArmOutput]:
    """Runs `g3_tabular_only` (no graph ablation) and `g3_hybrid_cs` (Ego-Graph + Tabular + C&S + PPR)."""
    cfg = GraphRiskConfig(hub_degree_cap=20, rarity_power=1.5)
    t0 = time.perf_counter()
    tr_g = build_bipartite_graph(accounts, reports, cutoff_ts=train_cutoff, config=cfg)
    va_g = build_bipartite_graph(accounts, reports, cutoff_ts=val_cutoff, config=cfg)

    fit_ids = [s for s in train_ids if (s in train_pos_seeds or s in train_neg_seeds)] if train_neg_seeds else list(train_ids)
    y_tr_obs = np.array([1 if s in train_pos_seeds else 0 for s in fit_ids], dtype=int)

    X_tr_tab = _extract_account_tabular_features(tr_g, scenario_ids, fit_ids)
    X_va_tab = _extract_account_tabular_features(va_g, scenario_ids, val_ids)

    t_tab0 = time.perf_counter()
    pred_tab, tab_params = _fit_pu_ensemble(X_tr_tab, y_tr_obs, X_va_tab, y_val)
    p_tab_va = pred_tab(X_va_tab)
    tab_val_sc = {s: float(p) for s, p in zip(val_ids, p_tab_va)}
    tab_thr = _pick_threshold(y_val, p_tab_va)
    t_tab1 = time.perf_counter()

    t_hyb0 = time.perf_counter()
    X_tr_hyb = np.hstack([X_tr_tab, _extract_seed_free_ego_features(tr_g, fit_ids)])
    X_va_hyb = np.hstack([X_va_tab, _extract_seed_free_ego_features(va_g, val_ids)])

    pred_hyb, hyb_params = _fit_pu_ensemble(X_tr_hyb, y_tr_obs, X_va_hyb, y_val)

    all_va_ids = va_g.account_ids
    X_all_va = np.hstack([
        _extract_account_tabular_features(va_g, scenario_ids, all_va_ids),
        _extract_seed_free_ego_features(va_g, all_va_ids),
    ])
    base_va_map = {s: float(p) for s, p in zip(all_va_ids, pred_hyb(X_all_va))}
    ppr_va = personalized_pagerank(va_g.W, _seed_indices(va_g, train_pos_seeds), alpha=0.70)
    ppr_va_map = _scores_to_dict(va_g, ppr_va, val_ids)

    best_fuse = (-1.0, 0.0, 0.0, 0.0, 0.0, {s: base_va_map.get(s, 0.0) for s in val_ids})
    for a1, a2, sc_cs in ((0.0, 0.0, 0.0), (0.50, 0.45, 0.60), (0.65, 0.60, 0.90)):
        if a1 == 0.0 and a2 == 0.0:
            cs_va = {s: base_va_map.get(s, 0.0) for s in val_ids}
        else:
            cs_arr = _correct_and_smooth(va_g, base_va_map, train_pos_seeds, train_neg_seeds,
                                         alpha1=a1, alpha2=a2, scale=sc_cs)
            cs_va = _scores_to_dict(va_g, cs_arr, val_ids)
        for gamma in (0.0, 0.15, 0.30, 0.45):
            fused = {s: (1.0 - gamma) * cs_va[s] + gamma * ppr_va_map[s] for s in val_ids}
            ap = _ap_safe(y_val, np.array([fused[s] for s in val_ids]))
            if ap > best_fuse[0]:
                best_fuse = (ap, a1, a2, sc_cs, gamma, fused)
    _, best_a1, best_a2, best_sc_cs, best_gamma, hyb_val_sc = best_fuse
    hyb_thr = _pick_threshold(y_val, np.array([hyb_val_sc[s] for s in val_ids]))
    t_hyb1 = time.perf_counter()

    t_i0 = time.perf_counter()
    te_g = build_bipartite_graph(accounts, reports, cutoff_ts=test_cutoff, config=cfg)

    X_te_tab = _extract_account_tabular_features(te_g, scenario_ids, test_ids)
    tab_test_sc = {s: float(p) for s, p in zip(test_ids, pred_tab(X_te_tab))}
    t_i1 = time.perf_counter()

    all_te_ids = te_g.account_ids
    X_all_te = np.hstack([
        _extract_account_tabular_features(te_g, scenario_ids, all_te_ids),
        _extract_seed_free_ego_features(te_g, all_te_ids),
    ])
    base_te_map = {s: float(p) for s, p in zip(all_te_ids, pred_hyb(X_all_te))}
    if best_a1 == 0.0 and best_a2 == 0.0:
        cs_te = {s: base_te_map.get(s, 0.0) for s in test_ids}
    else:
        cs_te_arr = _correct_and_smooth(te_g, base_te_map, train_pos_seeds, train_neg_seeds,
                                        alpha1=best_a1, alpha2=best_a2, scale=best_sc_cs)
        cs_te = _scores_to_dict(te_g, cs_te_arr, test_ids)
    ppr_te = personalized_pagerank(te_g.W, _seed_indices(te_g, train_pos_seeds), alpha=0.70)
    ppr_te_map = _scores_to_dict(te_g, ppr_te, test_ids)
    hyb_test_sc = {s: (1.0 - best_gamma) * cs_te[s] + best_gamma * ppr_te_map[s] for s in test_ids}
    t_i2 = time.perf_counter()

    reps_count_te: dict[str, int] = {}
    for r in te_g.reports:
        reps_count_te[r["_so_tk"]] = reps_count_te.get(r["_so_tk"], 0) + 1
    deg_te = np.asarray(te_g.W.sum(axis=1)).ravel()
    tab_abstain = {s: reps_count_te.get(s, 0) == 0 for s in test_ids}
    hyb_abstain = {
        s: (reps_count_te.get(s, 0) == 0 and (s not in te_g.account_index or deg_te[te_g.account_index[s]] == 0.0))
        for s in test_ids
    }

    arm_tab = NodeArmOutput(
        name="g3_tabular_only",
        val_scores=tab_val_sc, test_scores=tab_test_sc, threshold=tab_thr,
        best_params=tab_params,
        fit_ms=round((t_tab1 - t_tab0) * 1000.0, 2),
        infer_ms=round((t_i1 - t_i0) * 1000.0, 2),
        abstain_mask_test=tab_abstain,
    )
    arm_hyb = NodeArmOutput(
        name="g3_hybrid_cs",
        val_scores=hyb_val_sc, test_scores=hyb_test_sc, threshold=hyb_thr,
        best_params={**hyb_params, "cs_a1": best_a1, "cs_a2": best_a2, "cs_scale": best_sc_cs, "ppr_gamma": best_gamma},
        fit_ms=round((t_hyb1 - t_hyb0 + (t_tab0 - t0)) * 1000.0, 2),
        infer_ms=round((t_i2 - t_i1) * 1000.0, 2),
        abstain_mask_test=hyb_abstain,
    )
    return arm_tab, arm_hyb


# ---------------------------------------------------------------------------
# G4: Real Subgraph / Cluster Classification (1-WL Subtree Kernel + FRAUDAR Density)
# ---------------------------------------------------------------------------
def wl_subtree_feature_dict(
    cluster: dict[str, Any],
    graph: BipartiteGraph,
    *,
    n_iter: int = 2,
) -> dict[str, float]:
    """Explicit 1-Weisfeiler-Lehman (WL) Subtree Graph Kernel feature map (Shervashidze et al., JMLR 2011)."""
    accs = cluster["accounts"]
    ents = [("phone", p) for p in cluster["phones"]] + [("domain", d) for d in cluster["domains"]]
    ent_set = set(ents)

    acc_reps: dict[str, list[dict[str, Any]]] = {a: [] for a in accs}
    for r in cluster["reports"]:
        if r["_so_tk"] in acc_reps:
            acc_reps[r["_so_tk"]].append(r)

    adj: dict[str, list[str]] = {}
    labels: dict[str, str] = {}

    for a in accs:
        nid = f"A:{a}"
        adj[nid] = []
        loai = graph.account_meta.get(a, {}).get("loai") or "unk"
        rs = acc_reps[a]
        scam_frac = sum(1 for r in rs if r.get("muc") == "giong_chieu_lua") / max(len(rs), 1)
        verdict = "sc" if scam_frac >= 0.5 else ("mix" if scam_frac > 0 else "ord")
        labels[nid] = f"acc_{loai}_{verdict}"

    for ek in ents:
        nid = f"E:{ek[0]}:{ek[1]}"
        adj[nid] = []
        deg = graph.entity_degree.get(ek, 1)
        db = "d1" if deg == 1 else ("d2_4" if deg <= 4 else ("d5_10" if deg <= 10 else "d11p"))
        labels[nid] = f"ent_{ek[0]}_{db}"

    for a in accs:
        aid = f"A:{a}"
        for ek in graph.acc_to_ent.get(a, {}):
            if ek in ent_set:
                eid = f"E:{ek[0]}:{ek[1]}"
                adj[aid].append(eid)
                adj[eid].append(aid)

    counts: dict[str, float] = {}
    for lbl in labels.values():
        k = f"wl0:{lbl}"
        counts[k] = counts.get(k, 0.0) + 1.0

    cur = labels
    for it in range(1, n_iter + 1):
        nxt: dict[str, str] = {}
        for nid, lbl in cur.items():
            nbr_sig = ",".join(sorted(cur[u] for u in adj[nid]))
            digest = hashlib.blake2b(f"{lbl}|[{nbr_sig}]".encode("utf-8"), digest_size=6).hexdigest()
            token = f"wl{it}:{digest}"
            nxt[nid] = token
            counts[token] = counts.get(token, 0.0) + 1.0
        cur = nxt

    return counts


def cluster_structural_features(
    cluster: dict[str, Any],
    graph: BipartiteGraph,
) -> np.ndarray:
    """Seed-free subgraph structural, FRAUDAR density, temporal burstiness & scenario consensus features."""
    accs = cluster["accounts"]
    reps = cluster["reports"]
    ents = [("phone", p) for p in cluster["phones"]] + [("domain", d) for d in cluster["domains"]]
    ent_set = set(ents)

    n_acc = len(accs)
    n_ph = len(cluster["phones"])
    n_dom = len(cluster["domains"])
    n_ent = max(n_ph + n_dom, 1)
    n_rep = max(len(reps), 1)

    fraudar_edge_sum = 0.0
    n_bip_edges = 0
    for a in accs:
        for ek in graph.acc_to_ent.get(a, {}):
            if ek in ent_set:
                n_bip_edges += 1
                fraudar_edge_sum += 1.0 / math.log(graph.entity_degree.get(ek, 1) + 5.0)
    fraudar_density = fraudar_edge_sum / max(n_acc + n_ph + n_dom, 1)
    bip_density = n_bip_edges / max(n_acc * n_ent, 1)

    days = sorted(float(r["_ts"]) for r in reps)
    span = (days[-1] - days[0]) if len(days) > 1 else 0.0
    iqr = float(np.percentile(days, 75) - np.percentile(days, 25)) if len(days) > 1 else 0.0
    burst_rate = n_rep / (span + 1.0)

    scen_counts: dict[str, int] = {}
    for r in reps:
        kb = r.get("kich_ban") or "unknown"
        scen_counts[kb] = scen_counts.get(kb, 0) + 1
    scen_probs = np.array(list(scen_counts.values()), dtype=np.float64) / n_rep
    scen_entropy = float(-np.sum(scen_probs * np.log2(np.clip(scen_probs, 1e-12, 1.0))))

    frac_scam_rep = sum(1 for r in reps if r.get("muc") == "giong_chieu_lua") / n_rep
    frac_unc_rep = sum(1 for r in reps if r.get("muc") == "chua_du_can_cu") / n_rep
    frac_stop = sum(1 for r in reps if r.get("nut") == "dung_lai") / n_rep
    frac_mismatch = sum(1 for r in reps if r.get("ten_khop_tu_xung") == "khong") / n_rep
    frac_personal = sum(1 for a in accs if graph.account_meta.get(a, {}).get("loai") == "ca_nhan") / max(n_acc, 1)
    m3_vals = [float(r.get("m3_scam_prob", 0.5)) for r in reps]

    return np.array([
        math.log1p(n_acc),
        math.log1p(n_ph),
        math.log1p(n_dom),
        n_acc / n_ent,
        n_rep / max(n_acc, 1),
        bip_density,
        fraudar_density,
        math.log1p(span),
        math.log1p(iqr),
        burst_rate,
        scen_entropy,
        frac_scam_rep,
        frac_unc_rep,
        frac_stop,
        frac_mismatch,
        frac_personal,
        float(np.mean(m3_vals)),
        float(np.max(m3_vals)),
    ], dtype=np.float64)


def annotate_cluster_ground_truth(
    clusters: list[dict[str, Any]],
    gt_by_account: dict[str, dict[str, Any]],
    train_pos_seeds: set[str],
) -> list[dict[str, Any]]:
    """Attach ground-truth cluster labels & purity strictly for EVALUATION (never used in training)."""
    out = []
    for cl in clusters:
        accs = cl["accounts"]
        n_scam = sum(int(gt_by_account.get(a, {}).get("gt_is_scam", 0)) for a in accs)
        frac_scam = n_scam / max(len(accs), 1)
        is_scam_cluster = 1 if (n_scam >= 1 and frac_scam >= 0.5) else 0
        purity = max(frac_scam, 1.0 - frac_scam)
        has_seed = any(a in train_pos_seeds for a in accs)
        c2 = dict(cl)
        c2.update({
            "gt_n_scam_accounts": n_scam,
            "gt_frac_scam": round(frac_scam, 4),
            "gt_is_scam_cluster": is_scam_cluster,
            "gt_purity": round(purity, 4),
            "has_train_seed": has_seed,
            "gt_is_unseen_scam_ring": int(is_scam_cluster == 1 and not has_seed),
        })
        out.append(c2)
    return out


def run_g4_cluster_classification(
    accounts: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    gt_by_account: dict[str, dict[str, Any]],
    train_cutoff: float,
    val_cutoff: float,
    test_cutoff: float,
    train_pos_seeds: set[str],
) -> list[ClusterArmOutput]:
    """True Graph/Subgraph Classification on /staff/clusters components:
    1. `g4_naive_uf_count`  : Current /staff/clusters Union-Find (no hub filter)
    2. `g4_hubcut_uf_ppr`   : Hub-filtered Union-Find ranked by max PPR (exposes victim-phone percolation)
    3. `g4_louvain_max_ppr` : Hub-filtered Weighted Louvain communities ranked by max PPR
    4. `g4_louvain_wl`      : Hub-filtered Weighted Louvain communities classified via
                              1-WL Subtree Kernel + FRAUDAR density + scenario consensus
    """
    cfg = GraphRiskConfig(hub_degree_cap=20, rarity_power=1.5)
    tr_g = build_bipartite_graph(accounts, reports, cutoff_ts=train_cutoff, config=cfg)
    va_g = build_bipartite_graph(accounts, reports, cutoff_ts=val_cutoff, config=cfg)
    te_g = build_bipartite_graph(accounts, reports, cutoff_ts=test_cutoff, config=cfg)

    def _eligible(cls_list: list[dict[str, Any]], min_day_exclusive: float | None = None) -> list[dict[str, Any]]:
        res = []
        for cl in cls_list:
            if len(cl["accounts"]) < 2 and cl["n_reports"] < 2:
                continue
            if min_day_exclusive is not None and max(float(r["_ts"]) for r in cl["reports"]) <= min_day_exclusive:
                continue
            res.append(cl)
        return res

    ppr_va = personalized_pagerank(va_g.W, _seed_indices(va_g, train_pos_seeds), alpha=0.70)
    ppr_te = personalized_pagerank(te_g.W, _seed_indices(te_g, train_pos_seeds), alpha=0.70)

    def _max_ppr(cls_list: list[dict[str, Any]], g: BipartiteGraph, ppr: np.ndarray) -> np.ndarray:
        vals = []
        for c in cls_list:
            sc = [float(ppr[g.account_index[a]]) for a in c["accounts"] if a in g.account_index and a not in train_pos_seeds]
            vals.append(max(sc, default=0.0))
        return np.array(vals, dtype=np.float64)

    # ---- Baseline 1: g4_naive_uf_count (current app/main.py /staff/clusters) ----
    t0 = time.perf_counter()
    va_naive = annotate_cluster_ground_truth(
        _eligible(extract_clusters(va_g, remove_hubs=False), train_cutoff), gt_by_account, train_pos_seeds,
    )
    te_naive = annotate_cluster_ground_truth(
        _eligible(extract_clusters(te_g, remove_hubs=False), val_cutoff), gt_by_account, train_pos_seeds,
    )
    va_naive_sc = np.array([float(c["n_scam_reports"]) for c in va_naive], dtype=np.float64)
    te_naive_sc = np.array([float(c["n_scam_reports"]) for c in te_naive], dtype=np.float64)
    y_va_naive = np.array([c["gt_is_scam_cluster"] for c in va_naive], dtype=int)
    naive_thr = _pick_threshold(y_va_naive, va_naive_sc, target_fpr=0.05)
    dt_naive = (time.perf_counter() - t0) * 1000.0

    arm_naive = ClusterArmOutput(
        name="g4_naive_uf_count",
        val_clusters=va_naive, test_clusters=te_naive,
        val_scores=va_naive_sc, test_scores=te_naive_sc, threshold=naive_thr,
        best_params={"partition": "union_find_raw"}, fit_ms=0.0, infer_ms=round(dt_naive, 2),
    )

    # ---- Baseline 2: g4_hubcut_uf_ppr (hub-filtered Union-Find -> still percolates via victim bridges!) ----
    t0 = time.perf_counter()
    va_uf = annotate_cluster_ground_truth(
        _eligible(extract_clusters(va_g, remove_hubs=True), train_cutoff), gt_by_account, train_pos_seeds,
    )
    te_uf = annotate_cluster_ground_truth(
        _eligible(extract_clusters(te_g, remove_hubs=True), val_cutoff), gt_by_account, train_pos_seeds,
    )
    va_uf_sc = _max_ppr(va_uf, va_g, ppr_va)
    te_uf_sc = _max_ppr(te_uf, te_g, ppr_te)
    y_va_uf = np.array([c["gt_is_scam_cluster"] for c in va_uf], dtype=int)
    uf_thr = _pick_threshold(y_va_uf, va_uf_sc, target_fpr=0.05)
    dt_uf = (time.perf_counter() - t0) * 1000.0

    arm_uf_ppr = ClusterArmOutput(
        name="g4_hubcut_uf_ppr",
        val_clusters=va_uf, test_clusters=te_uf,
        val_scores=va_uf_sc, test_scores=te_uf_sc, threshold=uf_thr,
        best_params={"partition": "union_find_hubcut"}, fit_ms=0.0, infer_ms=round(dt_uf, 2),
    )

    # ---- Weighted Louvain communities (breaks weak victim-phone bridges cleanly!) ----
    tr_cls = _eligible(extract_louvain_communities(tr_g, resolution=1.25, seed=42))
    va_cls = annotate_cluster_ground_truth(
        _eligible(extract_louvain_communities(va_g, resolution=1.25, seed=42), train_cutoff),
        gt_by_account, train_pos_seeds,
    )
    te_cls = annotate_cluster_ground_truth(
        _eligible(extract_louvain_communities(te_g, resolution=1.25, seed=42), val_cutoff),
        gt_by_account, train_pos_seeds,
    )
    y_va_cl = np.array([c["gt_is_scam_cluster"] for c in va_cls], dtype=int)

    # ---- Baseline 3: g4_louvain_max_ppr ----
    t0 = time.perf_counter()
    va_ppr_sc = _max_ppr(va_cls, va_g, ppr_va)
    te_ppr_sc = _max_ppr(te_cls, te_g, ppr_te)
    ppr_cl_thr = _pick_threshold(y_va_cl, va_ppr_sc, target_fpr=0.05)
    dt_ppr_cl = (time.perf_counter() - t0) * 1000.0

    arm_louv_ppr = ClusterArmOutput(
        name="g4_louvain_max_ppr",
        val_clusters=va_cls, test_clusters=te_cls,
        val_scores=va_ppr_sc, test_scores=te_ppr_sc, threshold=ppr_cl_thr,
        best_params={"partition": "louvain_1.25", "hub_degree_cap": cfg.hub_degree_cap},
        fit_ms=0.0, infer_ms=round(dt_ppr_cl, 2),
    )

    # ---- Real Graph Classifier: g4_louvain_wl (1-WL Subtree Kernel + FRAUDAR + Behavioral Consensus) ----
    t_f0 = time.perf_counter()
    y_tr_obs = np.array([1 if any(a in train_pos_seeds for a in c["accounts"]) else 0 for c in tr_cls], dtype=int)

    tr_wl = [wl_subtree_feature_dict(c, tr_g, n_iter=2) for c in tr_cls]
    va_wl = [wl_subtree_feature_dict(c, va_g, n_iter=2) for c in va_cls]

    dv = DictVectorizer(sparse=True)
    tfidf = TfidfTransformer(sublinear_tf=True)
    X_tr_wl = tfidf.fit_transform(dv.fit_transform(tr_wl))
    X_va_wl = tfidf.transform(dv.transform(va_wl))

    X_tr_st = np.vstack([cluster_structural_features(c, tr_g) for c in tr_cls])
    X_va_st = np.vstack([cluster_structural_features(c, va_g) for c in va_cls])

    sc_st = StandardScaler()
    X_tr_all = sparse.hstack([sparse.csr_matrix(sc_st.fit_transform(X_tr_st)), X_tr_wl]).tocsr()
    X_va_all = sparse.hstack([sparse.csr_matrix(sc_st.transform(X_va_st)), X_va_wl]).tocsr()

    best_cl = (-1.0, 1.0, None, np.zeros(len(va_cls), dtype=np.float64))
    if len(np.unique(y_tr_obs)) >= 2:
        for C in (0.1, 0.5, 2.0):
            clf = LogisticRegression(C=C, class_weight="balanced", max_iter=1500, random_state=42)
            clf.fit(X_tr_all, y_tr_obs)
            p_va = clf.predict_proba(X_va_all)[:, 1]
            ap = _ap_safe(y_va_cl, p_va)
            if ap > best_cl[0]:
                best_cl = (ap, C, clf, p_va)
    clf_wl = best_cl[2]
    p_wl_va = best_cl[3]

    best_blend = (-1.0, 0.0, p_wl_va)
    for w_ppr in (0.0, 0.15, 0.30):
        blended = (1.0 - w_ppr) * p_wl_va + w_ppr * va_ppr_sc
        ap = _ap_safe(y_va_cl, blended)
        if ap > best_blend[0]:
            best_blend = (ap, w_ppr, blended)
    _, best_wppr, va_wl_sc = best_blend
    wl_thr = _pick_threshold(y_va_cl, va_wl_sc, target_fpr=0.05)
    t_f1 = time.perf_counter()

    t_i0 = time.perf_counter()
    te_wl = [wl_subtree_feature_dict(c, te_g, n_iter=2) for c in te_cls]
    X_te_wl = tfidf.transform(dv.transform(te_wl))
    X_te_st = sc_st.transform(np.vstack([cluster_structural_features(c, te_g) for c in te_cls]))
    X_te_all = sparse.hstack([sparse.csr_matrix(X_te_st), X_te_wl]).tocsr()
    p_wl_te = clf_wl.predict_proba(X_te_all)[:, 1] if clf_wl is not None else np.zeros(len(te_cls))
    te_wl_sc = (1.0 - best_wppr) * p_wl_te + best_wppr * te_ppr_sc
    t_i1 = time.perf_counter()

    arm_wl = ClusterArmOutput(
        name="g4_louvain_wl",
        val_clusters=va_cls, test_clusters=te_cls,
        val_scores=va_wl_sc, test_scores=te_wl_sc, threshold=wl_thr,
        best_params={"partition": "louvain_1.25", "wl_iterations": 2, "C": best_cl[1], "ppr_blend": best_wppr},
        fit_ms=round((t_f1 - t_f0) * 1000.0, 2), infer_ms=round((t_i1 - t_i0) * 1000.0, 2),
    )

    return [arm_naive, arm_uf_ppr, arm_louv_ppr, arm_wl]
