"""Render E7 benchmark results into a clean Markdown report (`experiments/E7/report.md`)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def write_report(results: dict[str, Any], out_path: Path) -> Path:
    lines: list[str] = [
        "# Báo cáo thí nghiệm E7: So sánh các phương pháp Đồ thị rủi ro & Phân loại cụm",
        "",
        "> **Ranh giới trung thực:** Toàn bộ số liệu dưới đây đo trên bộ đồ thị giả lập 90 ngày có kiểm soát "
        "(`e7/gen_graph.py`), nhằm kiểm chứng cơ chế, sức chống chịu trước siêu nút (`shopee.vn`, tổng đài), "
        "nhiễu trích xuất và đường dây mới — **không phải** độ chính xác trên tài khoản ngân hàng thật.",
        "",
    ]

    preset_names = list(results.keys())
    if len(preset_names) > 1:
        arm_names = [r["arm"] for r in results[preset_names[0]]["aggregate"]["node_summary"]]
        lines += [
            "## Tổng hợp nhanh PR-AUC (Node-level) trên tất cả kịch bản",
            "",
            "| Phương pháp | " + " | ".join(f"`{p}`" for p in preset_names) + " |",
            "|---|" + "---:|" * len(preset_names),
        ]
        for aname in arm_names:
            cells = []
            for p in preset_names:
                row = next(r for r in results[p]["aggregate"]["node_summary"] if r["arm"] == aname)
                cells.append(f"{row['pr_auc']:.3f}")
            lines.append(f"| `{aname}` | " + " | ".join(cells) + " |")
        lines.append("")

        cl_arm_names = [r["arm"] for r in results[preset_names[0]]["aggregate"]["cluster_summary"]]
        lines += [
            "## Tổng hợp nhanh Cluster PR-AUC (Graph/Subgraph Classification)",
            "",
            "| Phương pháp | " + " | ".join(f"`{p}`" for p in preset_names) + " |",
            "|---|" + "---:|" * len(preset_names),
        ]
        for aname in cl_arm_names:
            cells = []
            for p in preset_names:
                row = next(r for r in results[p]["aggregate"]["cluster_summary"] if r["arm"] == aname)
                cells.append(f"{row['cluster_pr_auc']:.3f}")
            lines.append(f"| `{aname}` | " + " | ".join(cells) + " |")
        lines.append("")

    for pname, payload in results.items():
        agg = payload["aggregate"]
        sc = agg["split_counts_mean"]
        lines += [
            f"## Kịch bản `{pname}` (trung bình {len(agg['seeds'])} seed: `{agg['seeds']}`)",
            "",
            f"- Train (Ngày 1–55): **{sc['train_reported']:.0f}** TK có báo cáo "
            f"(tem đỏ nhân viên: **{sc['train_pos_seeds']:.0f}**, tem xanh: **{sc['train_neg_seeds']:.0f}**)",
            f"- Validation (Ngày 56–70): **{sc['val_accounts']:.0f}** TK (**{sc['val_scams']:.0f}** lừa đảo)",
            f"- Test mù (Ngày 71–90): **{sc['test_accounts']:.0f}** TK (**{sc['test_scams']:.0f}** lừa đảo = "
            f"**{sc['test_seen_ring_scams']:.0f}** băng cũ + **{sc['test_unseen_ring_scams']:.0f}** băng mới tinh; "
            f"số hub bị cắt: **{sc['filtered_hubs_at_test']:.0f}**)",
            "",
            "### 1. Chấm điểm từng tài khoản (Node Classification / Ranking)",
            "",
            "| Phương pháp | PR-AUC | P@20 | P@50 | Recall@FPR≤1% | Bắt oan Shop | Bắt băng cũ | Bắt băng mới | Abstain | CPU ms |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in agg["node_summary"]:
            lines.append(
                f"| `{r['arm']}` | {r['pr_auc']:.3f} ± {r['pr_auc_std']:.3f} | {_pct(r['p_at_20'])} | "
                f"{_pct(r['p_at_50'])} | {_pct(r['recall_at_fpr1'])} | {_pct(r['honest_shop_fpr'])} | "
                f"{_pct(r['seen_ring_recall'])} | {_pct(r['unseen_ring_recall'])} | "
                f"{_pct(r['abstain_rate'])} | {r['infer_ms']:.1f} |"
            )

        lines += [
            "",
            "### 2. Phân loại cả cụm vụ việc (Subgraph / Graph Classification cho `/staff/clusters`)",
            "",
            "| Phương pháp | Cluster PR-AUC | P@10 | P@20 | F1 | Bắt cụm mới tinh | Bắt oan cụm thường | Độ tinh khiết | Cụm lớn nhất | CPU ms |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in agg["cluster_summary"]:
            lines.append(
                f"| `{r['arm']}` | {r['cluster_pr_auc']:.3f} ± {r['cluster_pr_auc_std']:.3f} | "
                f"{_pct(r['cluster_p_at_10'])} | {_pct(r['cluster_p_at_20'])} | {r['cluster_f1']:.3f} | "
                f"{_pct(r['unseen_ring_cluster_recall'])} | {_pct(r['benign_cluster_fpr'])} | "
                f"{_pct(r['mean_purity'])} | {r['max_cluster_size']:.0f} | {r['infer_ms']:.1f} |"
            )
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    p = Path("experiments/E7/results.json")
    write_report(json.loads(p.read_text(encoding="utf-8")), Path("experiments/E7/report.md"))
