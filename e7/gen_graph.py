"""Phase 1 (E7): Synthetic 90-day fraud graph generator grounded in the 25 repo scenarios.

Generates a reproducible mock account-entity-report graph containing realistic anti-fraud traps:
1. Popular benign mega-hubs (Shopee, Facebook, Zalo, Tiki, Lazada, GHN, ViettelPost, MoMo +
   named Shopee / delivery / bank hotlines) shared by both scammers and honest merchants.
2. Victim phone leakage (heterophily bridges accidentally connecting scammers to normal accounts).
3. Realistic Tier-1 / Tier-2 AI pipeline noise calibrated to EXPERIMENTS.md (E4/E5/E6):
   - Screenshot string dropout & extra leaked strings
   - Chat scenario false alarms on normal transfers & missed scams
   - "chua_du_can_cu" (uncertain) verdicts
4. Scam typologies & temporal dynamics across 90 days:
   - Shared burner-SIM rings
   - Phishing-domain campaigns
   - Mule account rotation across Days 1-55 (train) -> 56-70 (val) -> 71-90 (test)
   - Held-out brand-new cold-start rings (25%) with zero prior confirmed seeds
   - Hijacked normal accounts turning scam mid-horizon
5. Sparse human-confirmed scam seeds (`da_xac_nhan`) with realistic review delay, defaulting to
   Positive-Unlabeled (PU) mode (`verified_normal_frac=0.0`) to match app/main.py today.

Usage:
    python -m e7.gen_graph --preset base --seed 20261127 --out data/E7/base
    python -m e7.gen_graph --preset s1_hub_explosion --seed 20261127 --out data/E7/s1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.lookup import ORG_ROLES
from core.scenarios import load as load_scenarios

ROOT = Path(__file__).resolve().parent.parent

# Popular benign domains (shared by innocent merchants/users AND scammers trying to blend in)
POPULAR_BENIGN_DOMAINS: list[tuple[str, str]] = [
    ("shopee.vn", "e-commerce platform (Shopee)"),
    ("facebook.com", "social network (Facebook)"),
    ("zalo.me", "chat app (Zalo)"),
    ("tiki.vn", "e-commerce platform (Tiki)"),
    ("lazada.vn", "e-commerce platform (Lazada)"),
    ("ghn.vn", "delivery carrier (Giao Hang Nhanh)"),
    ("viettelpost.vn", "delivery carrier (Viettel Post)"),
    ("momo.vn", "e-wallet portal (MoMo)"),
]

# Popular shared hotlines (fake/synthetic 1900/1800-style numbers representing public support lines)
SHARED_HOTLINES: list[tuple[str, str]] = [
    ("19001221", "Shopee customer hotline"),
    ("1900636677", "GHN delivery hotline"),
    ("19008095", "Viettel Post delivery hotline"),
    ("19001088", "J&T Express delivery hotline"),
    ("1900545413", "Bank customer hotline A"),
    ("1800588822", "Bank customer hotline B"),
    ("1900545415", "E-wallet customer hotline"),
    ("19006035", "Tiki customer hotline"),
]

SCAM_DOMAIN_PREFIXES = [
    "san-dau-tu", "crypto-vip", "hoan-tien", "thu-hoi-von", "ctv-don-hang",
    "vneid-capnhat", "vay-nhanh-24h", "shipper-buu-cuc", "khuyen-mai-vip", "ngan-hang-xac-minh",
]
SCAM_TLDS = [".xyz", ".top", ".site", ".vip", ".online", ".click"]


@dataclass(frozen=True)
class GenPreset:
    name: str
    n_accounts: int = 3000
    scam_rate: float = 0.045             # ~4.5% total scam accounts (including hijacked accounts)
    horizon_days: int = 90               # 90-day timeline
    train_end_day: int = 55              # Days 1..55  = train / seed observation window
    val_end_day: int = 70                # Days 56..70 = validation / threshold tuning window
    heldout_ring_frac: float = 0.25      # 25% of scam rings are brand-new cold-start rings (> day 55)
    confirmed_scam_frac: float = 0.25    # Only ~25% of early scam accounts get human-confirmed seeds
    verified_normal_frac: float = 0.0    # 0.0 = PU mode (matches current app/main.py)
    n_popular_domains: int = 8           # All 8 popular domains (Shopee, Facebook, Zalo, ...)
    n_shared_hotlines: int = 8           # All 8 delivery / Shopee / bank hotlines
    hub_attach_prob_normal: float = 0.24
    hub_attach_prob_scam: float = 0.28
    victim_phone_leak_prob: float = 0.14
    camouflage_edge_prob: float = 0.20
    m1_string_dropout: float = 0.12      # Calibrated to E4 (~88% recall)
    m2_ordinary_false_alarm: float = 0.075  # Calibrated to E5/E10 (~7.5% ordinary false alarms)
    m2_scam_miss_rate: float = 0.07      # Calibrated to E5/E10 (~7% missed scams)
    m3_uncertain_rate: float = 0.16      # Calibrated to E6 (~16-18% chua_du_can_cu)
    hijack_frac: float = 0.006           # ~0.6% of all accounts are normal accounts hijacked mid-horizon


PRESETS: dict[str, GenPreset] = {
    "base": GenPreset(name="base"),
    "s1_hub_explosion": GenPreset(
        name="s1_hub_explosion",
        hub_attach_prob_normal=0.45,
        hub_attach_prob_scam=0.55,
        camouflage_edge_prob=0.38,
    ),
    "s2_high_heterophily": GenPreset(
        name="s2_high_heterophily",
        victim_phone_leak_prob=0.32,
        hijack_frac=0.015,
    ),
    "s3_heavy_noise": GenPreset(
        name="s3_heavy_noise",
        m1_string_dropout=0.24,
        victim_phone_leak_prob=0.22,
        m2_ordinary_false_alarm=0.14,
        m2_scam_miss_rate=0.15,
    ),
    "s4_sparse_imbalance": GenPreset(
        name="s4_sparse_imbalance",
        scam_rate=0.02,
        confirmed_scam_frac=0.15,
        hijack_frac=0.003,
    ),
    "s5_camouflage_drift": GenPreset(
        name="s5_camouflage_drift",
        camouflage_edge_prob=0.42,
        hub_attach_prob_scam=0.48,
        heldout_ring_frac=0.35,
    ),
    "s6_cold_start_heavy": GenPreset(
        name="s6_cold_start_heavy",
        heldout_ring_frac=0.50,
    ),
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _scenario_split() -> tuple[list[str], list[str], dict[str, Any]]:
    scen, issues = load_scenarios()
    assert not issues, f"Scenario load errors: {issues}"
    scam_ids = sorted(sid for sid, s in scen.items() if s.nhom == "lua_dao")
    ord_ids = sorted(sid for sid, s in scen.items() if s.nhom == "binh_thuong")
    return scam_ids, ord_ids, scen


def _make_distribution(
    rng: random.Random,
    top_sid: str,
    all_sids: list[str],
    top_prob: float,
) -> dict[str, float]:
    """Generate a realistic 25-scenario probability vector peaking at `top_sid`."""
    rem = max(0.0, 1.0 - top_prob)
    others = [s for s in all_sids if s != top_sid]
    runners = rng.sample(others, k=min(3, len(others)))
    raw = {s: rng.uniform(0.0005, 0.004) for s in others}
    for r in runners:
        raw[r] = rng.uniform(0.05, 0.25)
    s_raw = sum(raw.values()) or 1.0
    dist = {top_sid: round(top_prob, 4)}
    for s in others:
        dist[s] = round(rem * raw[s] / s_raw, 4)
    return dist


def generate_dataset(preset: GenPreset, seed: int = 20261127) -> dict[str, Any]:
    """Generate a deterministic 90-day synthetic fraud graph dataset in memory."""
    rng = random.Random(seed)
    scam_sids, ord_sids, scen_map = _scenario_split()
    all_sids = sorted(scam_sids + ord_sids)

    domain_scam_sids = [
        s for s in scam_sids
        if s in (
            "dau_tu_san_gia", "dich_vu_lay_lai_tien", "ctv_online",
            "vay_online_dong_phi_truoc", "mo_vi_tra_sau_nhan_hoa_hong", "gia_ngan_hang",
        )
    ] or scam_sids
    burner_scam_sids = [s for s in scam_sids if s not in domain_scam_sids] or scam_sids

    n_total_scam = max(30, int(round(preset.n_accounts * preset.scam_rate)))
    n_hijacked = max(2, min(n_total_scam // 5, int(round(preset.n_accounts * preset.hijack_frac))))
    n_ring_scam = n_total_scam - n_hijacked
    n_normal = preset.n_accounts - n_total_scam

    accounts: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    label_events: list[dict[str, Any]] = []

    ent_seq = 0
    acc_seq = 0

    def next_account_no() -> str:
        nonlocal acc_seq
        acc_seq += 1
        # Fake 0009... prefix so mock accounts can never match real bank accounts
        return f"0009{acc_seq:08d}"

    def add_entity(
        etype: str,
        value: str,
        gt_role: str,
        ring_id: str | None = None,
        description: str | None = None,
    ) -> str:
        nonlocal ent_seq
        ent_seq += 1
        entities.append({
            "entity_id": f"{etype}_{ent_seq:05d}",
            "type": etype,
            "value": value,
            "gt_entity_role": gt_role,
            "gt_ring_id": ring_id,
            "gt_description": description,
        })
        return value

    # ------------------------------------------------------------------
    # Step 1: Create shared mega-hubs (Shopee, Facebook, Zalo, delivery/bank hotlines)
    #         and a pool of victim phones (for heterophily leakage).
    # ------------------------------------------------------------------
    popular_domains = [
        add_entity("domain", dom, "popular_benign_domain", description=desc)
        for dom, desc in POPULAR_BENIGN_DOMAINS[:preset.n_popular_domains]
    ]
    shared_hotlines = [
        add_entity("phone", num, "shared_hotline", description=desc)
        for num, desc in SHARED_HOTLINES[:preset.n_shared_hotlines]
    ]

    n_victim_phones = max(40, preset.n_accounts // 35)
    victim_phones = [
        add_entity("phone", f"091{rng.randint(1000000, 9999999)}", "victim_phone",
                   description="victim phone accidentally extracted from chat screenshot")
        for _ in range(n_victim_phones)
    ]

    # ------------------------------------------------------------------
    # Step 2: Create scam rings (shared-burner rings + phishing-domain campaigns)
    #         with mule rotation and 25% held-out cold-start rings.
    # ------------------------------------------------------------------
    scam_accounts: list[dict[str, Any]] = []
    rings: list[dict[str, Any]] = []
    ring_idx = 0
    rem = n_ring_scam

    while rem > 0:
        ring_idx += 1
        ring_size = min(rem, rng.randint(6, 13))
        if rem - ring_size < 4:
            ring_size = rem
        rem -= ring_size

        rid = f"scam_ring_{ring_idx:03d}"
        is_phishing = (ring_idx % 2 == 0)
        main_scenario = rng.choice(domain_scam_sids if is_phishing else burner_scam_sids)
        alt_scenario = rng.choice(domain_scam_sids if is_phishing else burner_scam_sids)
        typology = "phishing_domain_campaign" if is_phishing else "shared_burner_ring"

        n_phones = rng.randint(2, 4)
        ring_phones = [
            add_entity("phone", f"098{ring_idx:03d}{k:04d}", "scammer_burner_phone", rid,
                       description=f"burner SIM for {rid}")
            for k in range(n_phones)
        ]
        ring_domains = []
        if is_phishing or rng.random() < 0.35:
            for k in range(rng.randint(1, 2)):
                dom_val = f"{rng.choice(SCAM_DOMAIN_PREFIXES)}-{ring_idx}-{k}{rng.choice(SCAM_TLDS)}"
                ring_domains.append(
                    add_entity("domain", dom_val, "phishing_domain", rid,
                               description=f"phishing site for {rid}")
                )

        rings.append({
            "ring_id": rid,
            "typology": typology,
            "main_scenario": main_scenario,
            "alt_scenario": alt_scenario,
            "phones": ring_phones,
            "domains": ring_domains,
            "size": ring_size,
            "is_heldout": False,
            "accounts": [],
        })

    # Hold out a fraction of rings so they ONLY appear after train_end_day with ZERO prior seeds
    n_heldout = max(1, int(round(len(rings) * preset.heldout_ring_frac)))
    heldout_set = set(rng.sample(range(len(rings)), k=min(n_heldout, max(1, len(rings) - 2))))
    for idx, r in enumerate(rings):
        r["is_heldout"] = idx in heldout_set

    for r in rings:
        n_org = max(1, int(round(r["size"] * 0.20)))
        for k in range(r["size"]):
            role = "scam_organizer" if k < n_org else "scam_mule"
            loai = "to_chuc" if (role == "scam_organizer" and rng.random() < 0.45) else "ca_nhan"
            if r["is_heldout"]:
                first_day = rng.randint(preset.train_end_day + 2, preset.horizon_days - 5)
            elif k < max(2, int(r["size"] * 0.55)):
                first_day = rng.randint(1, preset.train_end_day - 6)
            else:
                # Temporal mule rotation: fresh bank accounts appearing in val/test window
                first_day = rng.randint(preset.train_end_day + 1, preset.horizon_days - 4)

            acc = {
                "so_tk": next_account_no(),
                "loai": loai,
                "created_day": first_day,
                "gt_is_scam": 1,
                "gt_role": role,
                "gt_ring_id": r["ring_id"],
                "gt_is_heldout_ring": int(r["is_heldout"]),
            }
            accounts.append(acc)
            scam_accounts.append(acc)
            r["accounts"].append(acc)

    # ------------------------------------------------------------------
    # Step 3: Create normal accounts (merchants, family groups, standalone users)
    #         and hijacked accounts (normal early -> compromised into a scam ring later).
    # ------------------------------------------------------------------
    n_merchant = int(round(n_normal * 0.28))
    n_personal = n_normal - n_merchant

    normal_accounts: list[dict[str, Any]] = []
    benign_clusters: list[dict[str, Any]] = []
    b_idx = 0

    # 3a. Benign online-merchant clusters (heavily touch Shopee/Facebook/Zalo & delivery hotlines)
    m_rem = n_merchant
    while m_rem > 0:
        b_idx += 1
        csize = min(m_rem, rng.randint(10, 22))
        m_rem -= csize
        cid = f"benign_shop_cluster_{b_idx:03d}"
        local_phone = add_entity("phone", f"090{b_idx:03d}{rng.randint(1000, 9999)}", "benign_shared_phone", cid,
                                 description=f"legitimate shared shop/dispatch phone for {cid}")
        cl_accs = []
        for _ in range(csize):
            acc = {
                "so_tk": next_account_no(),
                "loai": "to_chuc" if rng.random() < 0.55 else "ca_nhan",
                "created_day": rng.randint(1, preset.horizon_days - 5),
                "gt_is_scam": 0,
                "gt_role": "normal_merchant",
                "gt_ring_id": cid,
                "gt_is_heldout_ring": 0,
            }
            accounts.append(acc)
            normal_accounts.append(acc)
            cl_accs.append(acc)
        benign_clusters.append({
            "cluster_id": cid,
            "kind": "merchant",
            "shared_phone": local_phone,
            "hub_domains": rng.sample(popular_domains, k=min(2, len(popular_domains))),
            "hub_hotlines": rng.sample(shared_hotlines, k=min(2, len(shared_hotlines))),
            "accounts": cl_accs,
        })

    # 3b. Benign family/friend clusters (prone to occasional false alarm "mao_danh_nguoi_quen")
    p_clustered = int(round(n_personal * 0.25))
    p_solo = n_personal - p_clustered
    while p_clustered > 0:
        b_idx += 1
        csize = min(p_clustered, rng.randint(3, 6))
        p_clustered -= csize
        cid = f"benign_family_cluster_{b_idx:03d}"
        fam_phone = add_entity("phone", f"093{b_idx:03d}{rng.randint(1000, 9999)}", "benign_shared_phone", cid,
                               description=f"family/friend contact phone for {cid}")
        cl_accs = []
        for _ in range(csize):
            acc = {
                "so_tk": next_account_no(),
                "loai": "ca_nhan",
                "created_day": rng.randint(1, preset.horizon_days - 5),
                "gt_is_scam": 0,
                "gt_role": "normal_personal",
                "gt_ring_id": cid,
                "gt_is_heldout_ring": 0,
            }
            accounts.append(acc)
            normal_accounts.append(acc)
            cl_accs.append(acc)
        benign_clusters.append({
            "cluster_id": cid,
            "kind": "family",
            "shared_phone": fam_phone,
            "hub_domains": [rng.choice(popular_domains)],
            "hub_hotlines": [rng.choice(shared_hotlines)],
            "accounts": cl_accs,
        })

    solo_personal: list[dict[str, Any]] = []
    for _ in range(p_solo):
        acc = {
            "so_tk": next_account_no(),
            "loai": "ca_nhan",
            "created_day": rng.randint(1, preset.horizon_days - 5),
            "gt_is_scam": 0,
            "gt_role": "normal_personal",
            "gt_ring_id": None,
            "gt_is_heldout_ring": 0,
        }
        accounts.append(acc)
        normal_accounts.append(acc)
        solo_personal.append(acc)

    # 3c. Hijacked accounts: behave normally before hijack_day, then get absorbed into an active scam ring
    seen_rings = [r for r in rings if not r["is_heldout"]]
    hijacked_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for _ in range(n_hijacked):
        hijack_day = rng.randint(preset.train_end_day + 1, preset.horizon_days - 8)
        target_ring = rng.choice(seen_rings)
        acc = {
            "so_tk": next_account_no(),
            "loai": "ca_nhan",
            "created_day": rng.randint(1, preset.train_end_day - 15),
            "hijack_day": hijack_day,
            "gt_is_scam": 1,
            "gt_role": "hijacked_account",
            "gt_ring_id": target_ring["ring_id"],
            "gt_is_heldout_ring": 0,
        }
        accounts.append(acc)
        hijacked_pairs.append((acc, target_ring))

    # ------------------------------------------------------------------
    # Step 4: Simulate 90 days of Tier-2 reports (`reports.jsonl`) with M1/M2/M3 noise.
    # ------------------------------------------------------------------
    rep_seq = 0

    def emit_report(
        acc: dict[str, Any],
        day: int,
        true_is_scam: bool,
        true_scenario: str,
        phones: list[str],
        domains: list[str],
        *,
        force_lookalike_fa: bool = False,
    ) -> None:
        nonlocal rep_seq
        rep_seq += 1

        # M1 OCR/VLM string dropout (simulates missed strings on blurry/real screenshots)
        obs_phones = [p for p in phones if rng.random() > preset.m1_string_dropout]
        obs_domains = [d for d in domains if rng.random() > preset.m1_string_dropout]

        # M1 victim-phone leakage (heterophily bridge across unrelated accounts)
        if rng.random() < preset.victim_phone_leak_prob:
            obs_phones.append(rng.choice(victim_phones))

        # M2/M3 scenario prediction noise calibrated to EXPERIMENTS.md E5/E6/E10
        roll = rng.random()
        if true_is_scam:
            if roll < preset.m2_scam_miss_rate:
                pred_sid = rng.choice(ord_sids)
                muc = "giong_binh_thuong"
                top_p = rng.uniform(0.52, 0.78)
                m3_scam_p = rng.uniform(0.15, 0.45)
            elif roll < preset.m2_scam_miss_rate + preset.m3_uncertain_rate:
                pred_sid = true_scenario if rng.random() < 0.75 else rng.choice(scam_sids)
                muc = "chua_du_can_cu"
                top_p = rng.uniform(0.32, 0.49)
                m3_scam_p = rng.uniform(0.42, 0.68)
            else:
                pred_sid = true_scenario if rng.random() < 0.82 else rng.choice(scam_sids)
                muc = "giong_chieu_lua"
                top_p = rng.uniform(0.60, 0.96)
                m3_scam_p = rng.uniform(0.65, 0.97)
        else:
            fa_prob = preset.m2_ordinary_false_alarm * (1.8 if force_lookalike_fa else 1.0)
            if roll < fa_prob:
                pred_sid = "mao_danh_nguoi_quen" if (force_lookalike_fa and rng.random() < 0.65) else rng.choice(scam_sids)
                muc = "giong_chieu_lua"
                top_p = rng.uniform(0.52, 0.82)
                m3_scam_p = rng.uniform(0.45, 0.78)
            elif roll < fa_prob + preset.m3_uncertain_rate:
                pred_sid = true_scenario if rng.random() < 0.70 else rng.choice(ord_sids)
                muc = "chua_du_can_cu"
                top_p = rng.uniform(0.30, 0.49)
                m3_scam_p = rng.uniform(0.20, 0.52)
            else:
                pred_sid = true_scenario if rng.random() < 0.85 else rng.choice(ord_sids)
                muc = "giong_binh_thuong"
                top_p = rng.uniform(0.58, 0.95)
                m3_scam_p = rng.uniform(0.03, 0.28)

        # User final decision button (`dung_lai`, `kiem_tra_them`, `van_chuyen`)
        if muc == "giong_chieu_lua":
            nut = rng.choices(["dung_lai", "kiem_tra_them", "van_chuyen"], weights=[0.58, 0.27, 0.15])[0]
        elif muc == "chua_du_can_cu":
            nut = rng.choices(["dung_lai", "kiem_tra_them", "van_chuyen"], weights=[0.25, 0.45, 0.30])[0]
        else:
            nut = rng.choices(["dung_lai", "kiem_tra_them", "van_chuyen"], weights=[0.08, 0.17, 0.75])[0]

        # Account type vs claimed role check (core.lookup.ten_khop_tu_xung)
        scen_obj = scen_map[pred_sid]
        tu_xung_opts = list(scen_obj.truong.get("tu_xung", {}).keys())
        tu_xung = tu_xung_opts[0] if tu_xung_opts else None
        if tu_xung in ORG_ROLES and acc["loai"]:
            ten_khop = "co" if acc["loai"] == "to_chuc" else "khong"
        else:
            ten_khop = None

        amount = int(round(math.exp(rng.uniform(math.log(200_000), math.log(45_000_000))), -4))
        dist = _make_distribution(rng, pred_sid, all_sids, top_p)

        reports.append({
            "id": rep_seq,
            "session_id": f"e7s_{rep_seq:06d}",
            "so_tk": acc["so_tk"],
            "day": day,
            "tao_luc": float(day),
            "muc": muc,
            "kich_ban": pred_sid,
            "nut": nut,
            "sdt": sorted(set(obs_phones)),
            "link": sorted(set(obs_domains)),
            "so_tien": amount,
            "m3_scam_prob": round(m3_scam_p, 4),
            "ten_khop_tu_xung": ten_khop,
            "phan_phoi": dist,
        })

    # 4a. Scam ring reports (bursty activity + occasional multiple hubs for camouflage)
    for r in rings:
        for acc in r["accounts"]:
            n_reps = rng.randint(2, 5) if acc["gt_role"] == "scam_organizer" else rng.randint(1, 4)
            base_day = acc["created_day"]
            for _ in range(n_reps):
                day = min(preset.horizon_days, max(1, base_day + rng.randint(0, 12)))
                phones = [rng.choice(r["phones"])]
                if len(r["phones"]) > 1 and rng.random() < 0.35:
                    phones.append(rng.choice(r["phones"]))
                domains = [rng.choice(r["domains"])] if r["domains"] and rng.random() < 0.80 else []
                # Scammer camouflage: mention popular hubs (Shopee, Facebook, Zalo, delivery hotlines)
                if rng.random() < preset.hub_attach_prob_scam:
                    domains.extend(rng.sample(popular_domains, k=rng.choices([1, 2], weights=[0.75, 0.25])[0]))
                if rng.random() < preset.camouflage_edge_prob:
                    phones.append(rng.choice(shared_hotlines))
                sid = r["main_scenario"] if rng.random() < 0.80 else r["alt_scenario"]
                emit_report(acc, day, True, sid, phones, domains)

    # 4b. Benign online-merchant & family look-alike cluster reports
    for cl in benign_clusters:
        for acc in cl["accounts"]:
            n_reps = rng.randint(1, 3) if cl["kind"] == "merchant" else rng.randint(1, 2)
            base_day = acc["created_day"]
            for _ in range(n_reps):
                day = min(preset.horizon_days, max(1, base_day + rng.randint(0, 20)))
                phones, domains = [], []
                if rng.random() < 0.45:
                    phones.append(cl["shared_phone"])
                if cl["kind"] == "merchant":
                    if rng.random() < preset.hub_attach_prob_normal * 1.4:
                        domains.append(rng.choice(cl["hub_domains"]))
                        if rng.random() < 0.30 and len(cl["hub_domains"]) > 1:
                            domains.append(cl["hub_domains"][1])
                    if rng.random() < preset.hub_attach_prob_normal:
                        phones.append(rng.choice(cl["hub_hotlines"]))
                    sid = rng.choice(["bt_mua_online_nguoi_ban_moi", "bt_tra_shipper_khi_nhan_hang", "bt_dat_coc_da_xem"])
                    emit_report(acc, day, False, sid, phones, domains, force_lookalike_fa=False)
                else:
                    if rng.random() < preset.hub_attach_prob_normal * 0.5:
                        domains.append(rng.choice(cl["hub_domains"]))
                    sid = rng.choice(["bt_chuyen_cho_nguoi_than", "bt_tra_tien_nguoi_ban_quen", "bt_mung_cuoi_gop_quy"])
                    emit_report(acc, day, False, sid, phones, domains, force_lookalike_fa=True)

    # 4c. Standalone normal personal accounts (~35% ever trigger a Tier-2 check over 90 days)
    for acc in solo_personal:
        if rng.random() > 0.35:
            continue
        n_reps = 1 if rng.random() < 0.82 else 2
        for _ in range(n_reps):
            day = rng.randint(1, preset.horizon_days)
            phones, domains = [], []
            if rng.random() < preset.hub_attach_prob_normal:
                domains.append(rng.choice(popular_domains))
            if rng.random() < preset.hub_attach_prob_normal * 0.5:
                phones.append(rng.choice(shared_hotlines))
            emit_report(acc, day, False, rng.choice(ord_sids), phones, domains)

    # 4d. Hijacked accounts: normal report early, then scam reports tied to a ring post-hijack
    for acc, target_ring in hijacked_pairs:
        hday = acc["hijack_day"]
        emit_report(
            acc,
            max(1, hday - rng.randint(5, 18)),
            False,
            rng.choice(ord_sids),
            [rng.choice(shared_hotlines)] if rng.random() < 0.4 else [],
            [rng.choice(popular_domains)] if rng.random() < 0.5 else [],
        )
        for _ in range(rng.randint(1, 3)):
            day = min(preset.horizon_days, hday + rng.randint(1, 10))
            phones = [rng.choice(target_ring["phones"])]
            domains = [rng.choice(target_ring["domains"])] if target_ring["domains"] else []
            emit_report(acc, day, True, target_ring["main_scenario"], phones, domains)

    reports.sort(key=lambda r: (r["day"], r["id"]))

    # ------------------------------------------------------------------
    # Step 5: Generate timestamped `label_events.jsonl` (staff confirmations + auto yellow flags).
    # ------------------------------------------------------------------
    first_report_day: dict[str, int] = {}
    for r in reports:
        if r["so_tk"] not in first_report_day:
            first_report_day[r["so_tk"]] = r["day"]

    early_scams = [
        a for a in scam_accounts
        if not a["gt_is_heldout_ring"]
        and a["so_tk"] in first_report_day
        and first_report_day[a["so_tk"]] <= preset.train_end_day - 3
    ]
    by_ring: dict[str, list[dict[str, Any]]] = {}
    for a in early_scams:
        by_ring.setdefault(a["gt_ring_id"], []).append(a)

    confirmed_scams: set[str] = set()
    for rid, members in sorted(by_ring.items()):
        members_sorted = sorted(
            members,
            key=lambda x: (0 if x["gt_role"] == "scam_organizer" else 1, first_report_day[x["so_tk"]]),
        )
        n_pick = max(1, int(round(len(members_sorted) * preset.confirmed_scam_frac)))
        for a in members_sorted[:n_pick]:
            confirmed_scams.add(a["so_tk"])
            confirm_day = min(preset.train_end_day, first_report_day[a["so_tk"]] + rng.randint(1, 4))
            label_events.append({
                "so_tk": a["so_tk"],
                "label": "da_xac_nhan",
                "by": "nhan_vien",
                "day": confirm_day,
            })

    verified_normals: set[str] = set()
    if preset.verified_normal_frac > 0:
        early_normals = [
            a for a in normal_accounts
            if a["so_tk"] in first_report_day and first_report_day[a["so_tk"]] <= preset.train_end_day - 3
        ]
        n_neg = max(1, int(round(len(early_normals) * preset.verified_normal_frac)))
        for a in rng.sample(early_normals, k=min(n_neg, len(early_normals))):
            verified_normals.add(a["so_tk"])
            confirm_day = min(preset.train_end_day, first_report_day[a["so_tk"]] + rng.randint(1, 4))
            label_events.append({
                "so_tk": a["so_tk"],
                "label": "verified_normal",
                "by": "nhan_vien",
                "day": confirm_day,
            })

    # Automatic weak flags (`dang_bi_bao_cao`) mirroring app/main.py line 128
    seen_weak: set[str] = set()
    for r in reports:
        sid = r["so_tk"]
        if r["muc"] == "giong_chieu_lua" and sid not in seen_weak:
            seen_weak.add(sid)
            label_events.append({
                "so_tk": sid,
                "label": "dang_bi_bao_cao",
                "by": "bao_cao_tu_dong",
                "day": r["day"],
            })

    label_events.sort(key=lambda e: (e["day"], e["so_tk"], e["label"]))

    # Compute hub degree audit stats so user can inspect real hub degrees right in graph_manifest.json
    ent_accounts: dict[tuple[str, str], set[str]] = {}
    for r in reports:
        for p in r["sdt"]:
            ent_accounts.setdefault(("phone", p), set()).add(r["so_tk"])
        for d in r["link"]:
            ent_accounts.setdefault(("domain", d), set()).add(r["so_tk"])

    role_lookup = {(e["type"], e["value"]): e["gt_entity_role"] for e in entities}
    top_hubs = sorted(
        [
            {
                "type": et,
                "value": val,
                "account_degree": len(accs),
                "gt_entity_role": role_lookup.get((et, val), "unknown"),
            }
            for (et, val), accs in ent_accounts.items()
        ],
        key=lambda x: -x["account_degree"],
    )[:20]

    # Temporal split preview counts (accounts with >= 1 report)
    split_counts = {"train_d1_55": 0, "val_d56_70": 0, "test_d71_90": 0, "never_reported": 0}
    scam_split = {"train_d1_55": 0, "val_d56_70": 0, "test_d71_90": 0, "never_reported": 0}
    for a in accounts:
        sid = a["so_tk"]
        if sid not in first_report_day:
            split_counts["never_reported"] += 1
            if a["gt_is_scam"]:
                scam_split["never_reported"] += 1
            continue
        eff_day = a["hijack_day"] if a["gt_role"] == "hijacked_account" else first_report_day[sid]
        bucket = "train_d1_55" if eff_day <= preset.train_end_day else (
            "val_d56_70" if eff_day <= preset.val_end_day else "test_d71_90"
        )
        split_counts[bucket] += 1
        if a["gt_is_scam"]:
            scam_split[bucket] += 1

    return {
        "preset": asdict(preset),
        "seed": seed,
        "accounts": accounts,
        "entities": entities,
        "reports": reports,
        "label_events": label_events,
        "summary": {
            "n_accounts": len(accounts),
            "n_scam_accounts": sum(a["gt_is_scam"] for a in accounts),
            "n_hijacked_accounts": len(hijacked_pairs),
            "n_normal_accounts": sum(1 - a["gt_is_scam"] for a in accounts),
            "scam_rate_actual": round(sum(a["gt_is_scam"] for a in accounts) / len(accounts), 4),
            "n_scam_rings": len(rings),
            "n_heldout_cold_start_rings": sum(1 for r in rings if r["is_heldout"]),
            "n_benign_clusters": len(benign_clusters),
            "n_entities": len(entities),
            "n_reports": len(reports),
            "n_train_confirmed_scam_seeds": len(confirmed_scams),
            "n_train_verified_normal_seeds": len(verified_normals),
            "n_auto_yellow_flags": len(seen_weak),
            "accounts_by_window": split_counts,
            "scams_by_window": scam_split,
            "top_20_entities_by_degree": top_hubs,
        },
    }


def save_dataset(data: dict[str, Any], out_dir: Path) -> Path:
    """Write JSONL tables + pretty-printed `graph_manifest.json` and `sample_preview.json`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for name in ("accounts", "entities", "reports", "label_events"):
        p = out_dir / f"{name}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for row in data[name]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        checksums[name] = _sha256_file(p)

    # Also write a compact, human-readable JSON preview showing concrete examples of each type
    by_role = {}
    for a in data["accounts"]:
        by_role.setdefault(a["gt_role"], a)
    by_ent_role = {}
    for e in data["entities"]:
        by_ent_role.setdefault(e["gt_entity_role"], e)
    preview = {
        "note": "Compact pretty-printed sample of generated mock records for manual inspection.",
        "summary": data["summary"],
        "sample_accounts_by_role": by_role,
        "sample_entities_by_role": by_ent_role,
        "sample_reports_first_5": data["reports"][:5],
        "sample_label_events_first_10": data["label_events"][:10],
    }
    (out_dir / "sample_preview.json").write_text(
        json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest = {
        "schema_version": "e7-synth-v1",
        "seed": data["seed"],
        "preset": data["preset"],
        "summary": data["summary"],
        "sha256": checksums,
    }
    mp = out_dir / "graph_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return mp


def load_dataset(data_dir: Path) -> dict[str, Any]:
    manifest = json.loads((data_dir / "graph_manifest.json").read_text(encoding="utf-8"))
    out = {"manifest": manifest, "preset": manifest["preset"], "seed": manifest["seed"], "summary": manifest["summary"]}
    for name in ("accounts", "entities", "reports", "label_events"):
        with (data_dir / f"{name}.jsonl").open("r", encoding="utf-8") as f:
            out[name] = [json.loads(line) for line in f if line.strip()]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate reproducible E7 synthetic fraud graph dataset (JSON/JSONL).")
    ap.add_argument("--preset", default="base", choices=sorted(PRESETS.keys()))
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--verified-normal-frac", type=float, default=None,
                    help="Override verified_normal_frac (e.g. 0.10 for 2-class mode vs 0.0 PU mode).")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    preset = PRESETS[args.preset]
    if args.verified_normal_frac is not None:
        preset = GenPreset(**{**asdict(preset), "verified_normal_frac": args.verified_normal_frac})
    out_dir = args.out or (ROOT / "data/E7" / args.preset)
    data = generate_dataset(preset, seed=args.seed)
    mp = save_dataset(data, out_dir)
    print(f"Saved {args.preset} (seed={args.seed}) -> {mp}")
    print(json.dumps(data["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
