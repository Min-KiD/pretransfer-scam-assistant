"""E7 Pure Graph Risk Engine (Account <-> Phone/Domain bipartite network).

Self-contained inside `e7/` (never opens or writes SQLite `account_labels`):
- Strict temporal cutoff (`cutoff_ts`) prevents future data leakage.
- Automatically detects & cuts mega-hubs (e.g., `shopee.vn`, delivery hotlines) above `hub_degree_cap`.
- Applies Adamic-Adar log-degree rarity penalty + recency decay on kept clues.
- Implements 4 classical graph propagation solvers on `scipy.sparse`:
  1. Absorbing-seed Fading-Ink Personalized PageRank (PU-native, bounded in [0, 1])
  2. Soft-clamp Label Spreading (Zhou et al., NeurIPS 2003)
  3. Hard-clamp Harmonic Label Propagation (Zhu et al., ICML 2003)
  4. Typed-Edge Linearized Belief Propagation with echo cancellation (LinBP / ZooBP)
- Multi-source Dijkstra evidence path extraction (`d = -log(w)`) with phone masking (`098***123`).
- Explicit 3-gate Abstain (`chua_du_can_cu`) + hub-safe cluster extraction.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import numpy as np
from scipy import sparse

from core.lookup import normalise_account


def normalise_phone(raw: str) -> str:
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if digits.startswith("84") and len(digits) >= 10:
        digits = "0" + digits[2:]
    return digits


def normalise_domain(raw: str) -> str:
    s = str(raw).strip().lower()
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.split("/", 1)[0].split("?", 1)[0].removeprefix("www.")


def mask_entity(entity_type: str, value: str) -> str:
    if entity_type == "phone" and len(value) >= 7:
        return f"{value[:3]}***{value[-3:]}"
    return value


@dataclass(frozen=True)
class GraphRiskConfig:
    hub_degree_cap: int = 20
    rarity_power: float = 1.5
    edge_weights: dict[str, float] = field(default_factory=lambda: {"phone": 1.0, "domain": 0.75})
    time_decay_per_day: float = 0.015
    ppr_alpha: float = 0.70
    spreading_alpha: float = 0.65
    weak_report_weight: float = 0.0
    max_hops: int = 3
    abstain_min_support: float = 0.08
    flag_threshold: float = 0.18
    time_unit_seconds: float | None = None


@dataclass
class BipartiteGraph:
    account_ids: list[str]
    account_index: dict[str, int]
    account_meta: dict[str, dict[str, Any]]
    entity_keys: list[tuple[str, str]]
    entity_index: dict[tuple[str, str], int]
    entity_degree: dict[tuple[str, str], int]
    entity_latest_ts: dict[tuple[str, str], float]
    filtered_hubs: list[dict[str, Any]]
    kept_entities: list[tuple[str, str]]
    acc_to_ent: dict[str, dict[tuple[str, str], dict[str, Any]]]
    ent_to_acc: dict[tuple[str, str], dict[str, dict[str, Any]]]
    acc_to_ent_all: dict[str, dict[tuple[str, str], dict[str, Any]]]
    ent_to_acc_all: dict[tuple[str, str], dict[str, dict[str, Any]]]
    reports: list[dict[str, Any]]
    ref_ts: float
    day_scale: float
    entity_weights: dict[tuple[str, str], float]
    W: sparse.csr_matrix
    W_by_type: dict[str, sparse.csr_matrix]


@dataclass
class GraphRiskResult:
    account_scores: dict[str, dict[str, Any]]
    clusters: list[dict[str, Any]]
    filtered_hubs: list[dict[str, Any]]
    stats: dict[str, Any]


def _extract_ts(rep: dict[str, Any]) -> float:
    for k in ("tao_luc", "observed_at", "ts", "day"):
        if k in rep and rep[k] is not None:
            return float(rep[k])
    return 0.0


def _extract_report_id(rep: dict[str, Any], fallback_idx: int) -> Any:
    for k in ("id", "report_id"):
        if k in rep and rep[k] is not None:
            return rep[k]
    return fallback_idx


def _extract_phones(rep: dict[str, Any]) -> list[str]:
    raw = rep.get("sdt") if "sdt" in rep else rep.get("phones", [])
    return sorted({normalise_phone(p) for p in (raw or []) if normalise_phone(p)})


def _extract_domains(rep: dict[str, Any]) -> list[str]:
    raw = rep.get("link") if "link" in rep else rep.get("domains", [])
    return sorted({normalise_domain(d) for d in (raw or []) if normalise_domain(d)})


def _infer_day_scale(timestamps: list[float], explicit: float | None) -> float:
    if explicit is not None:
        return max(float(explicit), 1e-9)
    if not timestamps:
        return 1.0
    return 86400.0 if max(timestamps) > 1e8 else 1.0


def _edge_bucket(entity_type: str, degree: int) -> str:
    return f"{entity_type}_{'rare' if degree <= 5 else 'mid'}"


def build_bipartite_graph(
    accounts: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    *,
    cutoff_ts: float | None = None,
    config: GraphRiskConfig | None = None,
) -> BipartiteGraph:
    """Build a temporally filtered Account <-> Phone/Domain bipartite graph and hub-penalised W."""
    cfg = config or GraphRiskConfig()

    acc_meta: dict[str, dict[str, Any]] = {}
    for a in accounts:
        sid = normalise_account(str(a["so_tk"]))
        if sid:
            acc_meta[sid] = dict(a)

    kept_reports: list[dict[str, Any]] = []
    ts_list: list[float] = []
    for idx, rep in enumerate(reports):
        ts = _extract_ts(rep)
        if cutoff_ts is not None and ts > cutoff_ts:
            continue
        sid = normalise_account(str(rep["so_tk"]))
        if not sid:
            continue
        if sid not in acc_meta:
            acc_meta[sid] = {"so_tk": sid, "loai": None, "nhan": "moi"}
        norm_rep = dict(rep)
        norm_rep["_so_tk"] = sid
        norm_rep["_ts"] = ts
        norm_rep["_rid"] = _extract_report_id(rep, idx)
        norm_rep["_phones"] = _extract_phones(rep)
        norm_rep["_domains"] = _extract_domains(rep)
        kept_reports.append(norm_rep)
        ts_list.append(ts)

    account_ids = sorted(acc_meta.keys())
    account_index = {sid: i for i, sid in enumerate(account_ids)}
    n_acc = len(account_ids)

    acc_to_ent_all: dict[str, dict[tuple[str, str], dict[str, Any]]] = {sid: {} for sid in account_ids}
    ent_to_acc_all: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    entity_latest_ts: dict[tuple[str, str], float] = {}

    for rep in kept_reports:
        sid, ts, rid = rep["_so_tk"], rep["_ts"], rep["_rid"]
        ents = [("phone", p) for p in rep["_phones"]] + [("domain", d) for d in rep["_domains"]]
        for ekey in ents:
            if ekey not in ent_to_acc_all:
                ent_to_acc_all[ekey] = {}
                entity_latest_ts[ekey] = ts
            else:
                entity_latest_ts[ekey] = max(entity_latest_ts[ekey], ts)

            edge = acc_to_ent_all[sid].get(ekey)
            if edge is None:
                edge = {"report_ids": [rid], "latest_ts": ts, "count": 1}
                acc_to_ent_all[sid][ekey] = edge
                ent_to_acc_all[ekey][sid] = edge
            else:
                edge["report_ids"].append(rid)
                edge["latest_ts"] = max(edge["latest_ts"], ts)
                edge["count"] += 1

    entity_keys = sorted(ent_to_acc_all.keys())
    entity_index = {ek: i for i, ek in enumerate(entity_keys)}
    entity_degree = {ek: len(ent_to_acc_all[ek]) for ek in entity_keys}

    ref_ts = float(cutoff_ts) if cutoff_ts is not None else (max(ts_list) if ts_list else 0.0)
    day_scale = _infer_day_scale(ts_list + ([ref_ts] if ref_ts > 0 else []), cfg.time_unit_seconds)

    filtered_hubs: list[dict[str, Any]] = []
    kept_entities: list[tuple[str, str]] = []
    entity_weights: dict[tuple[str, str], float] = {}

    for ek in entity_keys:
        deg = entity_degree[ek]
        etype, val = ek
        if deg > cfg.hub_degree_cap:
            filtered_hubs.append({
                "entity_type": etype,
                "value": val,
                "value_masked": mask_entity(etype, val),
                "degree": deg,
                "reason": f"degree {deg} > hub_degree_cap {cfg.hub_degree_cap}",
            })
            continue
        kept_entities.append(ek)
        base_w = cfg.edge_weights.get(etype, 0.5)
        age_days = max(0.0, (ref_ts - entity_latest_ts[ek]) / day_scale)
        recency = math.exp(-cfg.time_decay_per_day * age_days) if cfg.time_decay_per_day > 0 else 1.0
        rarity = 1.0 / (math.log(1.0 + max(deg, 1)) ** cfg.rarity_power)
        entity_weights[ek] = base_w * recency * rarity

    kept_set = set(kept_entities)
    acc_to_ent = {
        sid: {ek: info for ek, info in ed.items() if ek in kept_set}
        for sid, ed in acc_to_ent_all.items()
    }
    ent_to_acc = {ek: dict(ent_to_acc_all[ek]) for ek in kept_entities}

    def _project(entities_subset: list[tuple[str, str]]) -> sparse.csr_matrix:
        if n_acc == 0 or not entities_subset:
            return sparse.csr_matrix((n_acc, n_acc), dtype=np.float64)
        rows, cols, vals = [], [], []
        w_diag = np.zeros(len(entities_subset), dtype=np.float64)
        for col_i, ek in enumerate(entities_subset):
            if entity_degree[ek] < 2:
                continue
            w_diag[col_i] = entity_weights[ek]
            for sid, info in ent_to_acc[ek].items():
                rows.append(account_index[sid])
                cols.append(col_i)
                vals.append(1.0 + 0.15 * math.log1p(info["count"] - 1))
        if not rows:
            return sparse.csr_matrix((n_acc, n_acc), dtype=np.float64)
        B = sparse.csr_matrix((vals, (rows, cols)), shape=(n_acc, len(entities_subset)), dtype=np.float64)
        W_mat = (B @ sparse.diags(w_diag) @ B.T).tocsr()
        W_mat.setdiag(0.0)
        W_mat.eliminate_zeros()
        return W_mat

    W = _project(kept_entities)
    buckets: dict[str, list[tuple[str, str]]] = {
        "phone_rare": [], "phone_mid": [], "domain_rare": [], "domain_mid": [],
    }
    for ek in kept_entities:
        bname = _edge_bucket(ek[0], entity_degree[ek])
        if bname in buckets:
            buckets[bname].append(ek)
    W_by_type = {bname: _project(es) for bname, es in buckets.items()}

    return BipartiteGraph(
        account_ids=account_ids,
        account_index=account_index,
        account_meta=acc_meta,
        entity_keys=entity_keys,
        entity_index=entity_index,
        entity_degree=entity_degree,
        entity_latest_ts=entity_latest_ts,
        filtered_hubs=filtered_hubs,
        kept_entities=kept_entities,
        acc_to_ent=acc_to_ent,
        ent_to_acc=ent_to_acc,
        acc_to_ent_all=acc_to_ent_all,
        ent_to_acc_all=ent_to_acc_all,
        reports=kept_reports,
        ref_ts=ref_ts,
        day_scale=day_scale,
        entity_weights=entity_weights,
        W=W,
        W_by_type=W_by_type,
    )


def _row_normalise(W: sparse.csr_matrix) -> sparse.csr_matrix:
    deg = np.asarray(W.sum(axis=1)).ravel()
    inv = np.zeros_like(deg)
    nz = deg > 0
    inv[nz] = 1.0 / deg[nz]
    return sparse.diags(inv) @ W


def sym_normalise(W: sparse.csr_matrix) -> sparse.csr_matrix:
    deg = np.asarray(W.sum(axis=1)).ravel()
    inv_sqrt = np.zeros_like(deg)
    nz = deg > 0
    inv_sqrt[nz] = 1.0 / np.sqrt(deg[nz])
    D = sparse.diags(inv_sqrt)
    return (D @ W @ D).tocsr()


def personalized_pagerank(
    W: sparse.csr_matrix,
    positive_idx: list[int] | np.ndarray,
    *,
    alpha: float = 0.70,
    max_iter: int = 80,
    tol: float = 1e-7,
) -> np.ndarray:
    """Absorbing-seed fading-ink PPR (expected discounted hitting probability E[alpha^tau])."""
    n = W.shape[0]
    if n == 0 or len(positive_idx) == 0:
        return np.zeros(n, dtype=np.float64)
    P = _row_normalise(W)
    seed_mask = np.zeros(n, dtype=bool)
    seed_mask[np.asarray(positive_idx, dtype=int)] = True

    f = np.zeros(n, dtype=np.float64)
    f[seed_mask] = 1.0
    for _ in range(max_iter):
        f_next = alpha * (P @ f)
        f_next[seed_mask] = 1.0
        if np.max(np.abs(f_next - f)) < tol:
            f = f_next
            break
        f = f_next
    return np.clip(f, 0.0, 1.0)


def label_spreading(
    W: sparse.csr_matrix,
    positive_idx: list[int] | np.ndarray,
    *,
    negative_idx: list[int] | np.ndarray | None = None,
    weak_idx: list[int] | np.ndarray | None = None,
    weak_weight: float = 0.20,
    alpha: float = 0.65,
    max_iter: int = 100,
    tol: float = 1e-7,
) -> np.ndarray:
    """Soft-clamp Label Spreading (Zhou et al., NeurIPS 2003): F = alpha S F + (1 - alpha) Y."""
    n = W.shape[0]
    if n == 0 or (len(positive_idx) == 0 and not weak_idx):
        return np.zeros(n, dtype=np.float64)
    S = sym_normalise(W)
    has_neg = negative_idx is not None and len(negative_idx) > 0

    y = np.zeros(n, dtype=np.float64)
    if weak_idx is not None and len(weak_idx) > 0 and weak_weight != 0.0:
        y[np.asarray(weak_idx, dtype=int)] = float(weak_weight)
    if has_neg:
        y[np.asarray(negative_idx, dtype=int)] = -1.0
    if len(positive_idx) > 0:
        y[np.asarray(positive_idx, dtype=int)] = 1.0

    f = y.copy()
    for _ in range(max_iter):
        f_next = alpha * (S @ f) + (1.0 - alpha) * y
        if np.max(np.abs(f_next - f)) < tol:
            f = f_next
            break
        f = f_next

    if has_neg:
        return np.clip(0.5 * (f + 1.0), 0.0, 1.0)
    scale = max(float(np.max(f)), 1e-9)
    return np.clip(f / scale, 0.0, 1.0)


def hard_label_propagation(
    W: sparse.csr_matrix,
    positive_idx: list[int] | np.ndarray,
    negative_idx: list[int] | np.ndarray,
    *,
    max_iter: int = 150,
    tol: float = 1e-6,
) -> np.ndarray:
    """Harmonic hard-clamp Label Propagation (Zhu, Ghahramani & Lafferty, ICML 2003)."""
    n = W.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    P = _row_normalise(W)
    pos_mask = np.zeros(n, dtype=bool)
    neg_mask = np.zeros(n, dtype=bool)
    if len(positive_idx) > 0:
        pos_mask[np.asarray(positive_idx, dtype=int)] = True
    if len(negative_idx) > 0:
        neg_mask[np.asarray(negative_idx, dtype=int)] = True
    neg_mask &= ~pos_mask

    f = np.full(n, 0.5, dtype=np.float64)
    f[pos_mask] = 1.0
    f[neg_mask] = 0.0
    deg = np.asarray(W.sum(axis=1)).ravel()
    isolated = (deg == 0) & ~pos_mask & ~neg_mask
    f[isolated] = 0.0

    for _ in range(max_iter):
        f_next = P @ f
        f_next[pos_mask] = 1.0
        f_next[neg_mask] = 0.0
        f_next[isolated] = 0.0
        if np.max(np.abs(f_next - f)) < tol:
            f = f_next
            break
        f = f_next
    return np.clip(f, 0.0, 1.0)


def typed_linbp(
    W_by_type: dict[str, sparse.csr_matrix],
    positive_idx: list[int] | np.ndarray,
    *,
    negative_idx: list[int] | np.ndarray | None = None,
    weak_idx: list[int] | np.ndarray | None = None,
    h_by_type: dict[str, float] | None = None,
    weak_prior: float = 0.15,
    max_iter: int = 80,
    tol: float = 1e-6,
) -> np.ndarray:
    """Typed-Edge Linearized Belief Propagation (Gatterbauer et al. VLDB 2015; Eswaran et al. PVLDB 2017)."""
    any_W = next(iter(W_by_type.values()), None)
    if any_W is None or any_W.shape[0] == 0:
        return np.zeros(0, dtype=np.float64)
    n = any_W.shape[0]
    h_map = h_by_type or {
        "phone_rare": 0.45,
        "phone_mid": 0.15,
        "domain_rare": 0.35,
        "domain_mid": 0.08,
    }

    M = sparse.csr_matrix((n, n), dtype=np.float64)
    inf_norm_bound = 0.0
    for rtype, Wr in W_by_type.items():
        hr = float(h_map.get(rtype, 0.0))
        if abs(hr) < 1e-9 or Wr.nnz == 0:
            continue
        Ar = sym_normalise(Wr)
        dr = np.asarray(Ar.sum(axis=1)).ravel()
        Dr = sparse.diags(dr)
        Mr = hr * Ar - (hr * hr) * Dr
        M = (M + Mr).tocsr()
        inf_norm_bound += float(np.max(np.abs(Mr).sum(axis=1))) if Mr.nnz else 0.0

    if inf_norm_bound > 0.85:
        M = M * (0.85 / inf_norm_bound)

    e = np.zeros(n, dtype=np.float64)
    if weak_idx is not None and len(weak_idx) > 0 and weak_prior != 0.0:
        e[np.asarray(weak_idx, dtype=int)] = float(weak_prior)
    if negative_idx is not None and len(negative_idx) > 0:
        e[np.asarray(negative_idx, dtype=int)] = -1.0
    if len(positive_idx) > 0:
        e[np.asarray(positive_idx, dtype=int)] = 1.0

    b = e.copy()
    for _ in range(max_iter):
        b_next = e + (M @ b)
        if np.max(np.abs(b_next - b)) < tol:
            b = b_next
            break
        b = b_next

    has_neg = negative_idx is not None and len(negative_idx) > 0
    if has_neg:
        return 1.0 / (1.0 + np.exp(-np.clip(2.0 * b, -20.0, 20.0)))
    pos_b = np.maximum(b, 0.0)
    scale = max(float(np.max(pos_b)), 1e-9)
    return np.clip(pos_b / scale, 0.0, 1.0)


def find_evidence_paths(
    graph: BipartiteGraph,
    confirmed_scam_ids: set[str],
    *,
    max_hops: int = 3,
    top_k: int = 2,
) -> dict[str, list[dict[str, Any]]]:
    """Multi-source Dijkstra over the hub-filtered bipartite graph (`Account <-> Entity`)."""
    seeds = sorted(s for s in (normalise_account(x) for x in confirmed_scam_ids) if s in graph.account_index)
    if not seeds or not graph.kept_entities:
        return {}

    max_w = max(graph.entity_weights.values(), default=1.0)
    ent_reliability = {
        ek: min(0.95, max(1e-4, 0.95 * (w / max(max_w, 1e-9))))
        for ek, w in graph.entity_weights.items()
    }

    pq: list[tuple[float, int, str, str, tuple[tuple[str, str, str], ...]]] = []
    for s in seeds:
        heapq.heappush(pq, (0.0, 0, s, s, ()))

    found: dict[str, list[dict[str, Any]]] = {}
    seen_sig: dict[str, set[tuple[str, tuple[tuple[str, str], ...]]]] = {}

    while pq:
        cost, hops, acc, seed_id, via = heapq.heappop(pq)
        sig = (seed_id, tuple((et, val) for et, val, _ in via))
        if acc in found and len(found[acc]) >= top_k:
            continue
        if acc in seen_sig and sig in seen_sig[acc]:
            continue
        seen_sig.setdefault(acc, set()).add(sig)

        if hops > 0:
            via_records = []
            for etype, val, prev_acc in via:
                ek = (etype, val)
                reps_a = graph.acc_to_ent.get(prev_acc, {}).get(ek, {}).get("report_ids", [])
                via_records.append({
                    "entity_type": etype,
                    "entity_masked": mask_entity(etype, val),
                    "entity_degree": graph.entity_degree[ek],
                    "from_account": prev_acc,
                    "report_ids": sorted(set(reps_a))[:5],
                })
            if via_records:
                last_ek = (via[-1][0], via[-1][1])
                dst_reps = graph.acc_to_ent.get(acc, {}).get(last_ek, {}).get("report_ids", [])
                via_records[-1]["report_ids"] = sorted(set(via_records[-1]["report_ids"] + dst_reps))[:6]

            first_v = via_records[0]
            summary = (
                f"Lien he {hops} buoc toi STK xac nhan {seed_id} qua {first_v['entity_type']} "
                f"{first_v['entity_masked']} ({first_v['entity_degree']} STK dung chung, bao cao {first_v['report_ids']})"
            )
            found.setdefault(acc, []).append({
                "seed_account": seed_id,
                "hops": hops,
                "path_weight": round(math.exp(-cost), 4),
                "via": via_records,
                "summary": summary,
            })

        if hops >= max_hops:
            continue

        for ek in graph.acc_to_ent.get(acc, {}):
            step_cost = -math.log(ent_reliability[ek])
            next_cost = cost + step_cost
            etype, val = ek
            for nbr in graph.ent_to_acc.get(ek, {}):
                if nbr == acc or nbr == seed_id:
                    continue
                if nbr in found and len(found[nbr]) >= top_k:
                    continue
                if any(prev == nbr for _, _, prev in via):
                    continue
                heapq.heappush(pq, (next_cost, hops + 1, nbr, seed_id, via + ((etype, val, acc),)))

    return found


def extract_clusters(
    graph: BipartiteGraph,
    *,
    remove_hubs: bool = True,
) -> list[dict[str, Any]]:
    """Connected components over reports/accounts, optionally removing mega-hubs first."""
    reps = graph.reports
    if not reps:
        return []

    hub_set = {(h["entity_type"], h["value"]) for h in graph.filtered_hubs}
    parent = {i: i for i in range(len(reps))}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    owner: dict[tuple[str, str], int] = {}
    for idx, rep in enumerate(reps):
        keys = [("tk", rep["_so_tk"])]
        for p in rep["_phones"]:
            if not remove_hubs or ("phone", p) not in hub_set:
                keys.append(("phone", p))
        for d in rep["_domains"]:
            if not remove_hubs or ("domain", d) not in hub_set:
                keys.append(("domain", d))
        for k in keys:
            if k in owner:
                union(idx, owner[k])
            else:
                owner[k] = idx

    groups: dict[int, list[dict[str, Any]]] = {}
    for idx, rep in enumerate(reps):
        groups.setdefault(find(idx), []).append(rep)

    clusters: list[dict[str, Any]] = []
    for cid, grp in enumerate(sorted(groups.values(), key=lambda g: (-len(g), g[0]["_so_tk"]))):
        accs = sorted({r["_so_tk"] for r in grp})
        phones = sorted({p for r in grp for p in r["_phones"] if not remove_hubs or ("phone", p) not in hub_set})
        domains = sorted({d for r in grp for d in r["_domains"] if not remove_hubs or ("domain", d) not in hub_set})
        hubs_touched = sorted({
            f"{et}:{v}"
            for r in grp
            for et, v in ([("phone", p) for p in r["_phones"]] + [("domain", d) for d in r["_domains"]])
            if (et, v) in hub_set
        })
        n_scam_rep = sum(1 for r in grp if r.get("muc") == "giong_chieu_lua")
        clusters.append({
            "cluster_id": f"c_{cid:04d}",
            "accounts": accs,
            "phones": phones,
            "domains": domains,
            "report_ids": [r["_rid"] for r in grp],
            "reports": grp,
            "n_reports": len(grp),
            "n_scam_reports": n_scam_rep,
            "hubs_filtered_out": hubs_touched,
        })
    return clusters


def extract_louvain_communities(
    graph: BipartiteGraph,
    *,
    resolution: float = 1.25,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Partition the hub-filtered weighted account graph W using Louvain modularity optimisation.

    Even after cutting mega-hubs (Shopee/hotlines), a handful of low-degree victim phones acting
    as stray bridges can percolate dozens of unrelated clusters into one giant component.
    Weighted Louvain cuts weak single-bridge links and recovers tight scam rings & shop clusters.
    """
    if not graph.reports:
        return []

    hub_set = {(h["entity_type"], h["value"]) for h in graph.filtered_hubs}
    reps_by_acc: dict[str, list[dict[str, Any]]] = {}
    for r in graph.reports:
        reps_by_acc.setdefault(r["_so_tk"], []).append(r)

    reported_accs = sorted(reps_by_acc.keys())
    G_nx = nx.Graph()
    G_nx.add_nodes_from(reported_accs)

    W_coo = graph.W.tocoo()
    rep_set = set(reported_accs)
    for r_i, c_i, w in zip(W_coo.row, W_coo.col, W_coo.data):
        if r_i < c_i and w > 0:
            u, v = graph.account_ids[r_i], graph.account_ids[c_i]
            if u in rep_set and v in rep_set:
                G_nx.add_edge(u, v, weight=float(w))

    if G_nx.number_of_edges() > 0:
        comms = nx.community.louvain_communities(G_nx, weight="weight", resolution=resolution, seed=seed)
    else:
        comms = [{a} for a in reported_accs]

    clusters: list[dict[str, Any]] = []
    sorted_comms = sorted((sorted(c) for c in comms), key=lambda accs: (-len(accs), accs[0]))
    for cid, accs in enumerate(sorted_comms):
        grp = [r for a in accs for r in reps_by_acc[a]]
        grp.sort(key=lambda r: (r["_ts"], r["_rid"]))
        phones = sorted({p for r in grp for p in r["_phones"] if ("phone", p) not in hub_set})
        domains = sorted({d for r in grp for d in r["_domains"] if ("domain", d) not in hub_set})
        hubs_touched = sorted({
            f"{et}:{v}"
            for r in grp
            for et, v in ([("phone", p) for p in r["_phones"]] + [("domain", d) for d in r["_domains"]])
            if (et, v) in hub_set
        })
        n_scam_rep = sum(1 for r in grp if r.get("muc") == "giong_chieu_lua")
        clusters.append({
            "cluster_id": f"louv_{cid:04d}",
            "accounts": accs,
            "phones": phones,
            "domains": domains,
            "report_ids": [r["_rid"] for r in grp],
            "reports": grp,
            "n_reports": len(grp),
            "n_scam_reports": n_scam_rep,
            "hubs_filtered_out": hubs_touched,
        })
    return clusters


def score_account_graph(
    accounts: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    confirmed_scam_ids: set[str],
    verified_normal_ids: set[str] | None = None,
    *,
    weak_reported_ids: set[str] | None = None,
    method: str = "ppr",
    cutoff_ts: float | None = None,
    config: GraphRiskConfig | None = None,
) -> GraphRiskResult:
    """Pure read-only entry point returning scores, statuses, evidence trails, and clean clusters."""
    cfg = config or GraphRiskConfig()
    graph = build_bipartite_graph(accounts, reports, cutoff_ts=cutoff_ts, config=cfg)

    pos_set = {normalise_account(x) for x in confirmed_scam_ids}
    pos_idx = [graph.account_index[s] for s in sorted(pos_set) if s in graph.account_index]

    neg_set = {normalise_account(x) for x in (verified_normal_ids or set())} - pos_set
    neg_idx = [graph.account_index[s] for s in sorted(neg_set) if s in graph.account_index]

    weak_set = {normalise_account(x) for x in (weak_reported_ids or set())} - pos_set - neg_set
    weak_idx = [graph.account_index[s] for s in sorted(weak_set) if s in graph.account_index]

    if method == "ppr":
        raw_scores = personalized_pagerank(graph.W, pos_idx, alpha=cfg.ppr_alpha)
    elif method == "label_spreading":
        raw_scores = label_spreading(
            graph.W, pos_idx, negative_idx=neg_idx or None,
            weak_idx=weak_idx or None, weak_weight=cfg.weak_report_weight, alpha=cfg.spreading_alpha,
        )
    elif method == "hard_lp":
        raw_scores = hard_label_propagation(graph.W, pos_idx, neg_idx)
    elif method == "linbp":
        raw_scores = typed_linbp(
            graph.W_by_type, pos_idx, negative_idx=neg_idx or None,
            weak_idx=weak_idx or None, weak_prior=cfg.weak_report_weight,
        )
    else:
        raise ValueError(f"Unknown method: {method}")

    evidence = find_evidence_paths(graph, pos_set, max_hops=cfg.max_hops, top_k=2)
    row_support = np.asarray(graph.W.sum(axis=1)).ravel()

    account_scores: dict[str, dict[str, Any]] = {}
    for i, sid in enumerate(graph.account_ids):
        sc = float(raw_scores[i])
        sup = float(row_support[i])
        paths = evidence.get(sid, [])

        if sid in pos_set:
            status, reason = "confirmed_seed", None
        elif sid in neg_set:
            status, reason = "verified_normal_seed", None
        elif not paths:
            status, reason = "chua_du_can_cu", "no_path_within_max_hops"
        elif sup < cfg.abstain_min_support:
            status, reason = "chua_du_can_cu", "support_below_min_threshold"
        elif sc >= cfg.flag_threshold:
            status, reason = "can_nhan_vien_xem", None
        else:
            status, reason = "chua_du_can_cu", "score_below_flag_threshold"

        account_scores[sid] = {
            "so_tk": sid,
            "score": round(sc, 5),
            "status": status,
            "abstain_reason": reason,
            "support_weight": round(sup, 4),
            "n_kept_entities": len(graph.acc_to_ent.get(sid, {})),
            "evidence_paths": paths,
        }

    clusters = extract_clusters(graph, remove_hubs=True)
    for cl in clusters:
        unconfirmed = [account_scores[a]["score"] for a in cl["accounts"] if a not in pos_set]
        cl["max_account_score"] = round(max(unconfirmed, default=0.0), 5)
        cl["mean_account_score"] = round(float(np.mean(unconfirmed)) if unconfirmed else 0.0, 5)
        cl["has_confirmed_seed"] = any(a in pos_set for a in cl["accounts"])
    clusters.sort(key=lambda c: (-c["max_account_score"], -c["n_scam_reports"], -c["n_reports"]))

    return GraphRiskResult(
        account_scores=account_scores,
        clusters=clusters,
        filtered_hubs=graph.filtered_hubs,
        stats={
            "method": method,
            "n_accounts": len(graph.account_ids),
            "n_reports": len(graph.reports),
            "n_kept_entities": len(graph.kept_entities),
            "n_filtered_hubs": len(graph.filtered_hubs),
            "n_positive_seeds": len(pos_idx),
            "n_negative_seeds": len(neg_idx),
            "n_flagged": sum(1 for v in account_scores.values() if v["status"] == "can_nhan_vien_xem"),
            "n_abstained": sum(1 for v in account_scores.values() if v["status"] == "chua_du_can_cu"),
        },
    )
