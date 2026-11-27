"""E7 Leakage-Free Temporal & Held-Out Ring Evaluation Harness.

Usage:
    python -m e7.eval --preset base --seeds 20261127 20261128 20261129
    python -m e7.eval --sweep --seeds 20261127 20261128 20261129
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, f1_score, roc_curve

from core.scenarios import load as load_scenarios
from e7.gen_graph import PRESETS, GenPreset, generate_dataset
from e7.graph_engine import GraphRiskConfig, build_bipartite_graph
from e7.models import (
    ClusterArmOutput,
    NodeArmOutput,
    run_g0a_lookup,
    run_g0b_union_find,
    run_g0c_neighbor_count,
    run_g1a_weighted_lp,
    run_g1b_ppr,
    run_g2a_label_spreading,
    run_g2b_linbp,
    run_g3_hybrid_arms,
    run_g4_cluster_classification,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "experiments/E7"


def _precision_at_k(y_true: np.ndarray, scores: np.ndarray, k: int) -> float:
    """Tie-averaged exact expected Precision@K (prevents list-order bias when scores tie at 0.0)."""
    n = len(y_true)
    if n == 0:
        return 0.0
    k_eff = min(k, n)
    uniq_desc = np.unique(scores)[::-1]
    taken = 0
    expected_tp = 0.0
    for val in uniq_desc:
        mask = (scores == val)
        cnt = int(np.sum(mask))
        pos_in_tie = float(np.sum(y_true[mask]))
        if taken + cnt <= k_eff:
            expected_tp += pos_in_tie
            taken += cnt
        else:
            rem = k_eff - taken
            expected_tp += rem * (pos_in_tie / cnt)
            taken = k_eff
            break
    return float(expected_tp / k_eff)


def _recall_at_fpr(y_true: np.ndarray, scores: np.ndarray, max_fpr: float = 0.01) -> float:
    """Exact max TPR on the ROC curve where FPR <= max_fpr."""
    if len(y_true) == 0 or np.sum(y_true == 1) == 0 or np.sum(y_true == 0) == 0:
        return 0.0
    fpr, tpr, _ = roc_curve(y_true, scores)
    valid = fpr <= max_fpr + 1e-12
    return float(np.max(tpr[valid])) if np.any(valid) else 0.0


def _evaluate_node_arm(
    arm: NodeArmOutput,
    test_ids: list[str],
    gt_by_acc: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    y_true = np.array([int(gt_by_acc[s]["gt_is_scam"]) for s in test_ids], dtype=int)
    scores = np.array([arm.test_scores[s] for s in test_ids], dtype=np.float64)
    pred = scores >= arm.threshold

    pr_auc = float(average_precision_score(y_true, scores)) if 0 < np.sum(y_true) < len(y_true) else 0.0
    p20 = _precision_at_k(y_true, scores, 20)
    p50 = _precision_at_k(y_true, scores, 50)
    r_fpr1 = _recall_at_fpr(y_true, scores, 0.01)

    neg_mask = (y_true == 0)
    fpr_all = float(np.mean(pred[neg_mask])) if np.sum(neg_mask) else 0.0

    shop_mask = np.array([gt_by_acc[s]["gt_role"] == "normal_merchant" for s in test_ids], dtype=bool)
    shop_fpr = float(np.mean(pred[shop_mask])) if np.sum(shop_mask) else 0.0

    seen_scam = np.array([
        gt_by_acc[s]["gt_is_scam"] == 1 and not gt_by_acc[s].get("gt_is_heldout_ring", 0)
        for s in test_ids
    ], dtype=bool)
    unseen_scam = np.array([
        gt_by_acc[s]["gt_is_scam"] == 1 and bool(gt_by_acc[s].get("gt_is_heldout_ring", 0))
        for s in test_ids
    ], dtype=bool)
    seen_rec = float(np.mean(pred[seen_scam])) if np.sum(seen_scam) else 0.0
    unseen_rec = float(np.mean(pred[unseen_scam])) if np.sum(unseen_scam) else 0.0

    abstain = np.array([arm.abstain_mask_test.get(s, False) for s in test_ids], dtype=bool)
    abstain_rate = float(np.mean(abstain))
    covered_pred = pred & (~abstain)
    sel_prec = float(np.sum(covered_pred & (y_true == 1)) / max(int(np.sum(covered_pred)), 1)) if np.sum(covered_pred) else 0.0

    return {
        "arm": arm.name,
        "pr_auc": round(pr_auc, 4),
        "p_at_20": round(p20, 4),
        "p_at_50": round(p50, 4),
        "recall_at_fpr1": round(r_fpr1, 4),
        "fpr_all": round(fpr_all, 4),
        "honest_shop_fpr": round(shop_fpr, 4),
        "seen_ring_recall": round(seen_rec, 4),
        "unseen_ring_recall": round(unseen_rec, 4),
        "abstain_rate": round(abstain_rate, 4),
        "selective_precision": round(sel_prec, 4),
        "fit_ms": arm.fit_ms,
        "infer_ms": arm.infer_ms,
        "params": arm.best_params,
    }


def _evaluate_cluster_arm(arm: ClusterArmOutput) -> dict[str, Any]:
    cls = arm.test_clusters
    if not cls:
        return {"arm": arm.name, "n_test_clusters": 0}
    y_true = np.array([c["gt_is_scam_cluster"] for c in cls], dtype=int)
    scores = arm.test_scores
    pred = scores >= arm.threshold

    pr_auc = float(average_precision_score(y_true, scores)) if 0 < np.sum(y_true) < len(y_true) else 0.0
    p10 = _precision_at_k(y_true, scores, 10)
    p20 = _precision_at_k(y_true, scores, 20)
    f1 = float(f1_score(y_true, pred, zero_division=0))

    benign_mask = (y_true == 0)
    benign_fpr = float(np.mean(pred[benign_mask])) if np.sum(benign_mask) else 0.0

    unseen_mask = np.array([c["gt_is_unseen_scam_ring"] == 1 for c in cls], dtype=bool)
    unseen_rec = float(np.mean(pred[unseen_mask])) if np.sum(unseen_mask) else 0.0

    return {
        "arm": arm.name,
        "n_test_clusters": len(cls),
        "n_scam_clusters": int(np.sum(y_true)),
        "cluster_pr_auc": round(pr_auc, 4),
        "cluster_p_at_10": round(p10, 4),
        "cluster_p_at_20": round(p20, 4),
        "cluster_f1": round(f1, 4),
        "unseen_ring_cluster_recall": round(unseen_rec, 4),
        "benign_cluster_fpr": round(benign_fpr, 4),
        "mean_purity": round(float(np.mean([c["gt_purity"] for c in cls])), 4),
        "max_cluster_size": max(len(c["accounts"]) for c in cls),
        "fit_ms": arm.fit_ms,
        "infer_ms": arm.infer_ms,
        "params": arm.best_params,
    }


def run_single_seed(preset: GenPreset, seed: int) -> dict[str, Any]:
    """Run all node-level (G0..G3) and subgraph-level (G4) arms on one deterministic dataset."""
    data = generate_dataset(preset, seed=seed)
    scen_map, _ = load_scenarios()
    scenario_ids = sorted(scen_map.keys())

    accounts, reports, label_events = data["accounts"], data["reports"], data["label_events"]
    gt_by_acc = {a["so_tk"]: a for a in accounts}

    tr_end = float(preset.train_end_day)
    va_end = float(preset.val_end_day)
    te_end = float(preset.horizon_days)

    first_rep_day: dict[str, float] = {}
    for r in reports:
        sid, d = r["so_tk"], float(r["day"])
        if sid not in first_rep_day or d < first_rep_day[sid]:
            first_rep_day[sid] = d

    train_pos_seeds = {
        e["so_tk"] for e in label_events
        if e["label"] == "da_xac_nhan" and e["by"] == "nhan_vien" and e["day"] <= tr_end
    }
    train_neg_seeds = {
        e["so_tk"] for e in label_events
        if e["label"] == "verified_normal" and e["by"] == "nhan_vien" and e["day"] <= tr_end
    }
    val_weak_ids = {e["so_tk"] for e in label_events if e["label"] == "dang_bi_bao_cao" and e["day"] <= va_end}
    test_weak_ids = {e["so_tk"] for e in label_events if e["label"] == "dang_bi_bao_cao" and e["day"] <= te_end}

    train_ids, val_ids, test_ids = [], [], []
    for a in accounts:
        sid = a["so_tk"]
        if sid not in first_rep_day:
            continue
        eff_day = float(a["hijack_day"]) if a["gt_role"] == "hijacked_account" else first_rep_day[sid]
        if eff_day <= tr_end:
            train_ids.append(sid)
        elif eff_day <= va_end:
            val_ids.append(sid)
        else:
            test_ids.append(sid)

    val_ids = [s for s in val_ids if s not in train_pos_seeds and s not in train_neg_seeds]
    test_ids = [s for s in test_ids if s not in train_pos_seeds and s not in train_neg_seeds]
    y_val = np.array([int(gt_by_acc[s]["gt_is_scam"]) for s in val_ids], dtype=int)

    va_g0 = build_bipartite_graph(accounts, reports, cutoff_ts=va_end, config=GraphRiskConfig())
    te_g0 = build_bipartite_graph(accounts, reports, cutoff_ts=te_end, config=GraphRiskConfig())

    node_arms: list[NodeArmOutput] = [
        run_g0a_lookup(val_ids, test_ids, train_pos_seeds),
        run_g0b_union_find(va_g0, te_g0, val_ids, test_ids, train_pos_seeds),
        run_g0c_neighbor_count(va_g0, te_g0, val_ids, test_ids, y_val, train_pos_seeds),
        run_g1a_weighted_lp(accounts, reports, va_end, te_end, val_ids, test_ids, y_val, train_pos_seeds, train_neg_seeds),
        run_g1b_ppr(accounts, reports, va_end, te_end, val_ids, test_ids, y_val, train_pos_seeds),
        run_g2a_label_spreading(accounts, reports, va_end, te_end, val_ids, test_ids, y_val,
                                train_pos_seeds, train_neg_seeds, val_weak_ids, test_weak_ids),
        run_g2b_linbp(accounts, reports, va_end, te_end, val_ids, test_ids, y_val,
                      train_pos_seeds, train_neg_seeds, val_weak_ids, test_weak_ids),
    ]
    arm_tab, arm_hyb = run_g3_hybrid_arms(
        accounts, reports, scenario_ids, tr_end, va_end, te_end,
        train_ids, val_ids, test_ids, y_val, train_pos_seeds, train_neg_seeds,
    )
    node_arms.extend([arm_tab, arm_hyb])

    cluster_arms = run_g4_cluster_classification(
        accounts, reports, gt_by_acc, tr_end, va_end, te_end, train_pos_seeds,
    )

    test_scams = [s for s in test_ids if gt_by_acc[s]["gt_is_scam"] == 1]
    test_unseen = [s for s in test_scams if gt_by_acc[s].get("gt_is_heldout_ring", 0)]

    return {
        "preset": preset.name,
        "seed": seed,
        "split_counts": {
            "train_reported": len(train_ids),
            "train_pos_seeds": len(train_pos_seeds),
            "train_neg_seeds": len(train_neg_seeds),
            "val_accounts": len(val_ids),
            "val_scams": int(np.sum(y_val)),
            "test_accounts": len(test_ids),
            "test_scams": len(test_scams),
            "test_seen_ring_scams": len(test_scams) - len(test_unseen),
            "test_unseen_ring_scams": len(test_unseen),
            "filtered_hubs_at_test": len(te_g0.filtered_hubs),
        },
        "node_metrics": [_evaluate_node_arm(a, test_ids, gt_by_acc) for a in node_arms],
        "cluster_metrics": [_evaluate_cluster_arm(c) for c in cluster_arms],
    }


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    def _agg(key: str, fields: list[str]) -> list[dict[str, Any]]:
        by_arm: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for r in runs:
            for row in r[key]:
                name = row["arm"]
                if name not in by_arm:
                    by_arm[name] = []
                    order.append(name)
                by_arm[name].append(row)
        out = []
        for name in order:
            rows = by_arm[name]
            rec: dict[str, Any] = {"arm": name, "n_seeds": len(rows)}
            for mf in fields:
                vals = [float(x[mf]) for x in rows if mf in x]
                rec[mf] = round(float(np.mean(vals)), 4) if vals else 0.0
                rec[f"{mf}_std"] = round(float(np.std(vals)), 4) if len(vals) > 1 else 0.0
            out.append(rec)
        return out

    node_fields = [
        "pr_auc", "p_at_20", "p_at_50", "recall_at_fpr1", "fpr_all", "honest_shop_fpr",
        "seen_ring_recall", "unseen_ring_recall", "abstain_rate", "selective_precision", "infer_ms",
    ]
    cluster_fields = [
        "cluster_pr_auc", "cluster_p_at_10", "cluster_p_at_20", "cluster_f1",
        "unseen_ring_cluster_recall", "benign_cluster_fpr", "mean_purity", "max_cluster_size", "infer_ms",
    ]
    return {
        "preset": runs[0]["preset"],
        "seeds": [r["seed"] for r in runs],
        "split_counts_mean": {
            k: round(float(np.mean([r["split_counts"][k] for r in runs])), 1)
            for k in runs[0]["split_counts"]
        },
        "node_summary": _agg("node_metrics", node_fields),
        "cluster_summary": _agg("cluster_metrics", cluster_fields),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Run E7 benchmark (Node + Cluster Graph Classification).")
    ap.add_argument("--preset", default="base", choices=sorted(PRESETS.keys()))
    ap.add_argument("--sweep", action="store_true", help="Run base + S1..S6 + base_2class comparison.")
    ap.add_argument("--seeds", type=int, nargs="+", default=[20261127, 20261128, 20261129])
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    jobs: list[tuple[str, GenPreset]] = []
    if args.sweep:
        for pname, p in PRESETS.items():
            jobs.append((pname, p))
        jobs.append((
            "base_2class_10pct_neg",
            GenPreset(**{**asdict(PRESETS["base"]), "name": "base_2class_10pct_neg", "verified_normal_frac": 0.10}),
        ))
    else:
        jobs.append((args.preset, PRESETS[args.preset]))

    all_results: dict[str, Any] = {}
    for label, preset in jobs:
        runs = [run_single_seed(preset, s) for s in args.seeds]
        agg = aggregate_runs(runs)
        all_results[label] = {"aggregate": agg, "runs": runs}

        print(f"\n=== {label} (seeds={args.seeds}) ===")
        print("Split:", agg["split_counts_mean"])
        for row in agg["node_summary"]:
            print(
                f"  [NODE]    {row['arm']:20s} PR-AUC={row['pr_auc']:.3f} P@20={row['p_at_20']:.3f} "
                f"P@50={row['p_at_50']:.3f} ShopFPR={row['honest_shop_fpr']:.3f} "
                f"Seen={row['seen_ring_recall']:.3f} Unseen={row['unseen_ring_recall']:.3f} ({row['infer_ms']:.1f}ms)"
            )
        for row in agg["cluster_summary"]:
            print(
                f"  [CLUSTER] {row['arm']:20s} PR-AUC={row['cluster_pr_auc']:.3f} P@10={row['cluster_p_at_10']:.3f} "
                f"F1={row['cluster_f1']:.3f} Unseen={row['unseen_ring_cluster_recall']:.3f} "
                f"BenFPR={row['benign_cluster_fpr']:.3f} Purity={row['mean_purity']:.3f} MaxSz={row['max_cluster_size']:.0f}"
            )

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "results.json"
    out_json.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")

    from e7.report import write_report
    rep_path = write_report(all_results, args.out / "report.md")
    print(f"\nSaved {out_json} and {rep_path}")


if __name__ == "__main__":
    main()
