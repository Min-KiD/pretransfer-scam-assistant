"""E7 mock data, schema `e7-synth-v2`: a 90-day account / phone / link / report world for the account graph.

What one data set holds:
1. Receiving accounts: scam rings (small rings of 6-13 accounts, a few large rings of 28-50 accounts whose
   master phone sits on more than 20 accounts), ordinary shops, families, single users, and ordinary accounts
   taken over by a ring mid-way.
2. Phones and links read from chat screenshots: ring SIMs and sites, shop phones and shop sites, victims'
   own numbers leaking into reports, and public hubs (marketplaces, carriers, hotlines). `public_entities.json`
   lists the well-known hubs; a few hubs are deliberately missing from it, and a few shop phones are as widely
   shared as a large ring's master phone, so neither the list nor a degree cap alone separates them.
3. Reports: one per finished chat session, with the fields of the app's `reports` table. The chat verdict is
   drawn from the verdicts a real chat model gave on test set v2 for the same true scenario
   (`e7/chat_confusion.json`), so the mock chat fails where the measured model fails.
4. Labels over the whole 90 days: the app's automatic yellow flag, and a staff simulation with days off, a
   daily capacity and a minimum delay, which turns a flagged account red (`da_xac_nhan`) or clears it
   (`verified_normal`). `staff_calendar.jsonl` gives the working days so the loop can be replayed with another
   queue order.

Fields starting with `gt_` are answers for scoring only.

Usage:
    python -m e7.gen_graph --preset base --seed 20261127 --out data/E7/base
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.lookup import ORG_ROLES
from core.scenarios import load as load_scenarios
from e7.chat_confusion import load_table

ROOT = Path(__file__).resolve().parent.parent

# Well-known public hubs: every one of them is in `public_entities.json`.
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
# Public hubs that the list does not know: only their degree gives them away.
UNLISTED_BENIGN_DOMAINS: list[tuple[str, str]] = [
    ("tiktok.com", "social network and shop (TikTok), not in the public list"),
    ("chotot.com", "classified ads site (Cho Tot), not in the public list"),
]
UNLISTED_HOTLINES: list[tuple[str, str]] = [
    ("19002345", "regional courier hotline, not in the public list"),
    ("18006789", "telecom customer hotline, not in the public list"),
]

MOBILE_PREFIXES = ["090", "091", "093", "096", "097", "098", "032", "035", "038", "070", "079", "081"]
SCAM_DOMAIN_PREFIXES = [
    "san-dau-tu", "crypto-vip", "hoan-tien", "thu-hoi-von", "ctv-don-hang",
    "vneid-capnhat", "vay-nhanh-24h", "shipper-buu-cuc", "khuyen-mai-vip", "ngan-hang-xac-minh",
]
SCAM_TLDS = [".xyz", ".top", ".site", ".vip", ".online", ".click"]
SHOP_DOMAIN_WORDS = ["shop", "store", "nha", "tiem", "kho", "do-go", "my-pham", "thoi-trang", "gia-dung", "dien-may"]
SHOP_TLDS = [".vn", ".com", ".com.vn", ".store"]

STAFF_DAYS_OFF = (5, 6)  # day 1 is a Monday: days 6 and 7 of every week are off
UNLISTED_HUB_WEIGHT = 0.15  # an unlisted hub is picked this often relative to a listed one


@dataclass(frozen=True)
class GenPreset:
    name: str
    n_accounts: int = 8000
    scam_rate: float = 0.045             # scam accounts, taken-over accounts included
    horizon_days: int = 90
    train_end_day: int = 55              # days 1..55  = history
    val_end_day: int = 70                # days 56..70 = validation, 71..90 = test
    heldout_ring_frac: float = 0.25      # rings that first appear after `train_end_day`
    large_ring_frac: float = 0.12        # rings of 28-50 accounts with a master phone on more than 20 accounts
    large_merchant_frac: float = 0.06    # shop groups of 30-45 accounts behind one dispatch phone
    hub_attach_prob_normal: float = 0.24
    hub_attach_prob_scam: float = 0.28
    victim_phone_leak_prob: float = 0.14
    camouflage_edge_prob: float = 0.20
    m1_string_dropout: float = 0.12      # share of phones / links the screenshot reader misses (E4: about 88% found)
    chat_model: str = "flash_lite"       # row set of e7/chat_confusion.json the chat verdicts are drawn from
    hijack_frac: float = 0.006           # ordinary accounts taken over by a ring mid-way
    staff_capacity_per_day: int = 3      # accounts one working day of staff can review
    staff_absence_prob: float = 0.10     # chance that nobody reviews on a working day
    staff_min_delay_days: int = 1        # a flag is reviewed the next day at the earliest


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
        chat_model="qwen_untrained",
    ),
    "s4_sparse_imbalance": GenPreset(
        name="s4_sparse_imbalance",
        scam_rate=0.02,
        hijack_frac=0.003,
        staff_capacity_per_day=1,
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
    "s7_slow_staff": GenPreset(
        name="s7_slow_staff",
        staff_capacity_per_day=1,
        staff_absence_prob=0.35,
        staff_min_delay_days=3,
    ),
    "s8_chat_qwen_lora": GenPreset(
        name="s8_chat_qwen_lora",
        chat_model="qwen_lora",
    ),
    # Scoring only: another seed and other settings than every set above, never tuned on.
    "holdout_mixed": GenPreset(
        name="holdout_mixed",
        heldout_ring_frac=0.35,
        large_ring_frac=0.20,
        hub_attach_prob_normal=0.30,
        hub_attach_prob_scam=0.36,
        victim_phone_leak_prob=0.18,
        camouflage_edge_prob=0.28,
        m1_string_dropout=0.15,
        staff_capacity_per_day=2,
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
    """A 25-scenario probability vector peaking at `top_sid`."""
    rem = max(0.0, 1.0 - top_prob)
    others = [s for s in all_sids if s != top_sid]
    runners = rng.sample(others, k=min(3, len(others)))
    raw = {s: rng.uniform(0.0005, 0.004) for s in others}
    for r in runners:
        raw[r] = rng.uniform(0.05, 0.25)
    s_raw = sum(raw.values())
    # `kich_ban` is the top of this vector in the app, so no runner-up may pass it (an unsure verdict has a low top)
    while rem * max(raw.values()) / s_raw >= top_prob:
        raw[max(raw, key=raw.get)] /= 2
        s_raw = sum(raw.values())
    dist = {top_sid: round(top_prob, 4)}
    for s in others:
        dist[s] = round(rem * raw[s] / s_raw, 4)
    return dist


def staff_working_days(preset: GenPreset, seed: int) -> list[dict[str, Any]]:
    """The staff calendar of a data set: weekends off, plus days when nobody reviews."""
    rng = random.Random(f"{seed}-staff-calendar")
    days = []
    for day in range(1, preset.horizon_days + 1):
        working = (day - 1) % 7 not in STAFF_DAYS_OFF and rng.random() >= preset.staff_absence_prob
        days.append({"day": day, "working": working, "capacity": preset.staff_capacity_per_day if working else 0})
    return days


def staff_outcome(account: dict[str, Any], day: int) -> str:
    """What a staff review of `account` on `day` finds. Staff are taken to be right every time."""
    if account["gt_role"] == "hijacked_account":
        return "da_xac_nhan" if day >= account["gt_hijack_day"] else "verified_normal"
    return "da_xac_nhan" if account["gt_is_scam"] else "verified_normal"


def simulate_labels(
    preset: GenPreset,
    accounts: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    calendar: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Label history of the app as it runs today, without M4.

    During the day every report that ends in `giong_chieu_lua` puts a yellow flag on its account, unless the
    account is already yellow or red (app/main.py). At the end of a working day staff review the flagged accounts
    that have waited `staff_min_delay_days`, most scam verdicts first, then oldest flag, up to the day's capacity.
    A cleared account that gets a new scam verdict is flagged again.
    """
    by_acc = {a["so_tk"]: a for a in accounts}
    by_day: dict[int, list[dict[str, Any]]] = {}
    for r in reports:
        by_day.setdefault(r["day"], []).append(r)

    events: list[dict[str, Any]] = []
    label: dict[str, str] = {}
    flagged_day: dict[str, int] = {}
    n_scam_verdicts: Counter[str] = Counter()

    for cal in calendar:
        day = cal["day"]
        for r in by_day.get(day, []):
            if r["muc"] != "giong_chieu_lua":
                continue
            sid = r["so_tk"]
            n_scam_verdicts[sid] += 1
            if label.get(sid) in ("dang_bi_bao_cao", "da_xac_nhan"):
                continue
            label[sid] = "dang_bi_bao_cao"
            flagged_day[sid] = day
            events.append({"so_tk": sid, "label": "dang_bi_bao_cao", "by": "bao_cao_tu_dong",
                           "day": day, "report_id": r["id"]})

        waiting = sorted(
            (s for s, lab in label.items()
             if lab == "dang_bi_bao_cao" and flagged_day[s] <= day - preset.staff_min_delay_days),
            key=lambda s: (-n_scam_verdicts[s], flagged_day[s], s),
        )
        for sid in waiting[:cal["capacity"]]:
            label[sid] = staff_outcome(by_acc[sid], day)
            events.append({"so_tk": sid, "label": label[sid], "by": "nhan_vien",
                           "day": day, "flagged_day": flagged_day[sid]})
    return events


def generate_dataset(preset: GenPreset, seed: int = 20261127) -> dict[str, Any]:
    """Generate one deterministic data set in memory."""
    rng = random.Random(seed)
    scam_sids, ord_sids, scen_map = _scenario_split()
    all_sids = sorted(scam_sids + ord_sids)
    chat_table = load_table(preset.chat_model)
    assert set(chat_table) == set(all_sids), "chat table and scenario catalogue disagree"

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

    ent_seq = 0
    acc_seq = 0
    used_phones: set[str] = set()

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

    def new_mobile() -> str:
        """A mobile number whose digits say nothing about who owns it."""
        while True:
            num = f"{rng.choice(MOBILE_PREFIXES)}{rng.randint(0, 9_999_999):07d}"
            if num not in used_phones:
                used_phones.add(num)
                return num

    # ------------------------------------------------------------------
    # Step 1: public hubs (listed and unlisted) and the pool of victims' own numbers.
    # ------------------------------------------------------------------
    popular_domains = [
        add_entity("domain", dom, "popular_benign_domain", description=desc)
        for dom, desc in POPULAR_BENIGN_DOMAINS + UNLISTED_BENIGN_DOMAINS
    ]
    shared_hotlines = [
        add_entity("phone", num, "shared_hotline", description=desc)
        for num, desc in SHARED_HOTLINES + UNLISTED_HOTLINES
    ]
    public_entities = (
        [{"type": "domain", "value": dom, "description": desc} for dom, desc in POPULAR_BENIGN_DOMAINS]
        + [{"type": "phone", "value": num, "description": desc} for num, desc in SHARED_HOTLINES]
    )
    hub_weight = {v: 1.0 for v, _ in POPULAR_BENIGN_DOMAINS + SHARED_HOTLINES}
    hub_weight.update({v: UNLISTED_HUB_WEIGHT for v, _ in UNLISTED_BENIGN_DOMAINS + UNLISTED_HOTLINES})

    def pick_hubs(pool: list[str], k: int = 1) -> list[str]:
        """`k` different hubs. Unlisted hubs are less popular, so their degree falls among shops and rings."""
        left, picked = list(pool), []
        for _ in range(k):
            hub = rng.choices(left, weights=[hub_weight[h] for h in left])[0]
            left.remove(hub)
            picked.append(hub)
        return picked

    n_victim_phones = max(40, preset.n_accounts // 35)
    victim_phones = [
        add_entity("phone", new_mobile(), "victim_phone",
                   description="victim's own number, read from the chat screenshot by accident")
        for _ in range(n_victim_phones)
    ]

    # ------------------------------------------------------------------
    # Step 2: scam rings. Small rings share 2-4 SIMs; a large ring adds a master phone used by most of its
    #         accounts. Some rings only appear after `train_end_day`.
    # ------------------------------------------------------------------
    scam_accounts: list[dict[str, Any]] = []
    rings: list[dict[str, Any]] = []
    ring_idx = 0
    rem = n_ring_scam
    large_every = round(1 / preset.large_ring_frac) if preset.large_ring_frac > 0 else 0

    while rem > 0:
        ring_idx += 1
        is_large = bool(large_every) and ring_idx % large_every == 3 % large_every
        ring_size = min(rem, rng.randint(28, 50) if is_large else rng.randint(6, 13))
        if rem - ring_size < 4:
            ring_size = rem
        rem -= ring_size

        rid = f"scam_ring_{ring_idx:03d}"
        is_phishing = rng.random() < 0.5
        main_scenario = rng.choice(domain_scam_sids if is_phishing else burner_scam_sids)
        alt_scenario = rng.choice(domain_scam_sids if is_phishing else burner_scam_sids)

        ring_phones = [
            add_entity("phone", new_mobile(), "scammer_burner_phone", rid, description=f"SIM of {rid}")
            for _ in range(rng.randint(4, 8) if is_large else rng.randint(2, 4))
        ]
        master_phone = (
            add_entity("phone", new_mobile(), "scammer_master_phone", rid,
                       description=f"contact number most accounts of {rid} point to")
            if is_large else None
        )
        ring_domains = []
        if is_phishing or rng.random() < 0.35:
            for k in range(rng.randint(1, 2)):
                dom_val = f"{rng.choice(SCAM_DOMAIN_PREFIXES)}-{ring_idx}-{k}{rng.choice(SCAM_TLDS)}"
                ring_domains.append(
                    add_entity("domain", dom_val, "phishing_domain", rid, description=f"site of {rid}")
                )

        rings.append({
            "ring_id": rid,
            "is_large": is_large,
            "main_scenario": main_scenario,
            "alt_scenario": alt_scenario,
            "phones": ring_phones,
            "master_phone": master_phone,
            "domains": ring_domains,
            "size": ring_size,
            "is_heldout": False,
            "accounts": [],
        })

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
                # The ring moves to fresh bank accounts in the validation / test window
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
    # Step 3: ordinary accounts (shop groups, families, single users) and accounts taken over mid-way.
    # ------------------------------------------------------------------
    n_merchant = int(round(n_normal * 0.28))
    n_personal = n_normal - n_merchant

    normal_accounts: list[dict[str, Any]] = []
    benign_clusters: list[dict[str, Any]] = []
    b_idx = 0

    # 3a. Shop groups. A few are large: one dispatch phone serves 30-45 shop accounts.
    m_rem = n_merchant
    while m_rem > 0:
        b_idx += 1
        is_large = rng.random() < preset.large_merchant_frac
        csize = min(m_rem, rng.randint(30, 45) if is_large else rng.randint(10, 22))
        m_rem -= csize
        cid = f"benign_shop_cluster_{b_idx:03d}"
        local_phone = add_entity("phone", new_mobile(), "benign_shared_phone", cid,
                                 description=f"shop / dispatch phone of {cid}")
        shop_domain = None
        if rng.random() < 0.35:
            dom_val = f"{rng.choice(SHOP_DOMAIN_WORDS)}-{rng.choice(SHOP_DOMAIN_WORDS)}{b_idx}{rng.choice(SHOP_TLDS)}"
            shop_domain = add_entity("domain", dom_val, "benign_shop_domain", cid, description=f"own site of {cid}")
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
            "share_prob": 0.75 if is_large else 0.45,
            "shop_domain": shop_domain,
            "hub_domains": pick_hubs(popular_domains, 2),
            "hub_hotlines": pick_hubs(shared_hotlines, 2),
            "accounts": cl_accs,
        })

    # 3b. Families and friends
    p_clustered = int(round(n_personal * 0.25))
    p_solo = n_personal - p_clustered
    while p_clustered > 0:
        b_idx += 1
        csize = min(p_clustered, rng.randint(3, 6))
        p_clustered -= csize
        cid = f"benign_family_cluster_{b_idx:03d}"
        fam_phone = add_entity("phone", new_mobile(), "benign_shared_phone", cid,
                               description=f"family / friend contact phone of {cid}")
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
            "share_prob": 0.45,
            "shop_domain": None,
            "hub_domains": pick_hubs(popular_domains),
            "hub_hotlines": pick_hubs(shared_hotlines),
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

    # 3c. Taken-over accounts: ordinary before `gt_hijack_day`, part of a known ring after it
    seen_rings = [r for r in rings if not r["is_heldout"]]
    hijacked_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for _ in range(n_hijacked):
        hijack_day = rng.randint(preset.train_end_day + 1, preset.horizon_days - 8)
        target_ring = rng.choice(seen_rings)
        acc = {
            "so_tk": next_account_no(),
            "loai": "ca_nhan",
            "created_day": rng.randint(1, preset.train_end_day - 15),
            "gt_hijack_day": hijack_day,
            "gt_is_scam": 1,
            "gt_role": "hijacked_account",
            "gt_ring_id": target_ring["ring_id"],
            "gt_is_heldout_ring": 0,
        }
        accounts.append(acc)
        hijacked_pairs.append((acc, target_ring))

    # ------------------------------------------------------------------
    # Step 4: 90 days of reports, one per finished chat session.
    # ------------------------------------------------------------------
    def emit_report(
        acc: dict[str, Any],
        day: int,
        true_is_scam: bool,
        true_scenario: str,
        phones: list[str],
        domains: list[str],
    ) -> None:
        # Screenshot reader misses some strings and sometimes picks up the victim's own number
        obs_phones = [p for p in phones if rng.random() > preset.m1_string_dropout]
        obs_domains = [d for d in domains if rng.random() > preset.m1_string_dropout]
        if rng.random() < preset.victim_phone_leak_prob:
            obs_phones.append(rng.choice(victim_phones))

        # Chat verdict: one of the endings the measured chat model gave for this true scenario
        rows = chat_table[true_scenario]
        muc, pred_sid, _ = rng.choices(rows, weights=[n for _, _, n in rows])[0]
        if muc == "giong_chieu_lua":
            top_p = rng.uniform(0.60, 0.96)
            nut = rng.choices(["dung_lai", "kiem_tra_them", "van_chuyen"], weights=[0.58, 0.27, 0.15])[0]
        elif muc == "chua_du_can_cu":
            top_p = rng.uniform(0.32, 0.49)
            nut = rng.choices(["dung_lai", "kiem_tra_them", "van_chuyen"], weights=[0.25, 0.45, 0.30])[0]
        else:
            top_p = rng.uniform(0.58, 0.95)
            nut = rng.choices(["dung_lai", "kiem_tra_them", "van_chuyen"], weights=[0.08, 0.17, 0.75])[0]

        # Account type against the role the other side claims (core.lookup.ten_khop_tu_xung)
        tu_xung_opts = list(scen_map[pred_sid].truong.get("tu_xung", {}).keys())
        tu_xung = tu_xung_opts[0] if tu_xung_opts else None
        if tu_xung in ORG_ROLES and acc["loai"]:
            ten_khop = "co" if acc["loai"] == "to_chuc" else "khong"
        else:
            ten_khop = None

        amount = int(round(math.exp(rng.uniform(math.log(200_000), math.log(45_000_000))), -4))
        reports.append({
            "so_tk": acc["so_tk"],
            "day": day,
            "tao_luc": round(day - 1 + rng.random(), 5),
            "muc": muc,
            "kich_ban": pred_sid,
            "nut": nut,
            "sdt": sorted(set(obs_phones)),
            "link": sorted(set(obs_domains)),
            "so_tien": amount,
            "ten_khop_tu_xung": ten_khop,
            "phan_phoi": _make_distribution(rng, pred_sid, all_sids, top_p),
            "gt_is_scam": int(true_is_scam),
            "gt_kich_ban": true_scenario,
        })

    # 4a. Ring accounts: a burst of sessions, sometimes with public hubs mixed in
    for r in rings:
        for acc in r["accounts"]:
            n_reps = rng.randint(2, 5) if acc["gt_role"] == "scam_organizer" else rng.randint(1, 4)
            base_day = acc["created_day"]
            for _ in range(n_reps):
                day = min(preset.horizon_days, max(1, base_day + rng.randint(0, 12)))
                phones = [rng.choice(r["phones"])]
                if rng.random() < 0.35:
                    phones.append(rng.choice(r["phones"]))
                if r["master_phone"] and rng.random() < 0.65:
                    phones.append(r["master_phone"])
                domains = [rng.choice(r["domains"])] if r["domains"] and rng.random() < 0.80 else []
                if rng.random() < preset.hub_attach_prob_scam:
                    domains.extend(pick_hubs(popular_domains, rng.choices([1, 2], weights=[0.75, 0.25])[0]))
                if rng.random() < preset.camouflage_edge_prob:
                    phones.extend(pick_hubs(shared_hotlines))
                sid = r["main_scenario"] if rng.random() < 0.80 else r["alt_scenario"]
                emit_report(acc, day, True, sid, phones, domains)

    # 4b. Shop groups and families
    for cl in benign_clusters:
        for acc in cl["accounts"]:
            n_reps = rng.randint(1, 3) if cl["kind"] == "merchant" else rng.randint(1, 2)
            base_day = acc["created_day"]
            for _ in range(n_reps):
                day = min(preset.horizon_days, max(1, base_day + rng.randint(0, 20)))
                phones, domains = [], []
                if rng.random() < cl["share_prob"]:
                    phones.append(cl["shared_phone"])
                if cl["kind"] == "merchant":
                    if cl["shop_domain"] and rng.random() < 0.30:
                        domains.append(cl["shop_domain"])
                    if rng.random() < preset.hub_attach_prob_normal * 1.4:
                        domains.append(rng.choice(cl["hub_domains"]))
                        if rng.random() < 0.30:
                            domains.append(cl["hub_domains"][1])
                    if rng.random() < preset.hub_attach_prob_normal:
                        phones.append(rng.choice(cl["hub_hotlines"]))
                    sid = rng.choice(["bt_mua_online_nguoi_ban_moi", "bt_tra_shipper_khi_nhan_hang", "bt_dat_coc_da_xem"])
                else:
                    if rng.random() < preset.hub_attach_prob_normal * 0.5:
                        domains.append(rng.choice(cl["hub_domains"]))
                    sid = rng.choice(["bt_chuyen_cho_nguoi_than", "bt_tra_tien_nguoi_ban_quen", "bt_mung_cuoi_gop_quy"])
                emit_report(acc, day, False, sid, phones, domains)

    # 4c. Single users: about 35% ever open a check in 90 days
    for acc in solo_personal:
        if rng.random() > 0.35:
            continue
        n_reps = 1 if rng.random() < 0.82 else 2
        for _ in range(n_reps):
            day = rng.randint(1, preset.horizon_days)
            phones, domains = [], []
            if rng.random() < preset.hub_attach_prob_normal:
                domains.extend(pick_hubs(popular_domains))
            if rng.random() < preset.hub_attach_prob_normal * 0.5:
                phones.extend(pick_hubs(shared_hotlines))
            emit_report(acc, day, False, rng.choice(ord_sids), phones, domains)

    # 4d. Taken-over accounts: an ordinary session first, ring sessions after the take-over
    for acc, target_ring in hijacked_pairs:
        hday = acc["gt_hijack_day"]
        emit_report(
            acc,
            max(1, hday - rng.randint(5, 18)),
            False,
            rng.choice(ord_sids),
            pick_hubs(shared_hotlines) if rng.random() < 0.4 else [],
            pick_hubs(popular_domains) if rng.random() < 0.5 else [],
        )
        for _ in range(rng.randint(1, 3)):
            day = min(preset.horizon_days, hday + rng.randint(1, 10))
            phones = [rng.choice(target_ring["phones"])]
            domains = [rng.choice(target_ring["domains"])] if target_ring["domains"] else []
            emit_report(acc, day, True, target_ring["main_scenario"], phones, domains)

    # Report ids follow time: a smaller id is an earlier session
    reports.sort(key=lambda r: r["tao_luc"])
    reports = [{"id": i, "session_id": f"e7s_{i:06d}", **r} for i, r in enumerate(reports, start=1)]

    # ------------------------------------------------------------------
    # Step 5: label history (automatic yellow flags + staff reviews over the whole horizon).
    # ------------------------------------------------------------------
    calendar = staff_working_days(preset, seed)
    label_events = simulate_labels(preset, accounts, reports, calendar)
    for cal in calendar:
        cal["reviewed"] = sum(1 for e in label_events if e["by"] == "nhan_vien" and e["day"] == cal["day"])

    staff_events = [e for e in label_events if e["by"] == "nhan_vien"]
    final_label: dict[str, str] = {}
    for e in label_events:
        final_label[e["so_tk"]] = e["label"]
    delays = [e["day"] - e["flagged_day"] for e in staff_events]

    # ------------------------------------------------------------------
    # Summary for graph_manifest.json
    # ------------------------------------------------------------------
    first_report_day: dict[str, int] = {}
    ent_accounts: dict[tuple[str, str], set[str]] = {}
    for r in reports:
        first_report_day.setdefault(r["so_tk"], r["day"])
        for p in r["sdt"]:
            ent_accounts.setdefault(("phone", p), set()).add(r["so_tk"])
        for d in r["link"]:
            ent_accounts.setdefault(("domain", d), set()).add(r["so_tk"])

    role_lookup = {(e["type"], e["value"]): e["gt_entity_role"] for e in entities}
    degrees_by_role: dict[str, list[int]] = {}
    for key, accs in ent_accounts.items():
        degrees_by_role.setdefault(role_lookup[key], []).append(len(accs))
    top_hubs = sorted(
        [
            {"type": et, "value": val, "account_degree": len(accs), "gt_entity_role": role_lookup[(et, val)]}
            for (et, val), accs in ent_accounts.items()
        ],
        key=lambda x: -x["account_degree"],
    )[:20]

    split_counts = {"train_d1_55": 0, "val_d56_70": 0, "test_d71_90": 0, "never_reported": 0}
    scam_split = dict(split_counts)
    for a in accounts:
        sid = a["so_tk"]
        if sid not in first_report_day:
            split_counts["never_reported"] += 1
            scam_split["never_reported"] += a["gt_is_scam"]
            continue
        eff_day = a["gt_hijack_day"] if a["gt_role"] == "hijacked_account" else first_report_day[sid]
        bucket = "train_d1_55" if eff_day <= preset.train_end_day else (
            "val_d56_70" if eff_day <= preset.val_end_day else "test_d71_90"
        )
        split_counts[bucket] += 1
        scam_split[bucket] += a["gt_is_scam"]

    verdicts = Counter((r["gt_is_scam"], r["muc"]) for r in reports)
    return {
        "preset": asdict(preset),
        "seed": seed,
        "accounts": accounts,
        "entities": entities,
        "reports": reports,
        "label_events": label_events,
        "staff_calendar": calendar,
        "public_entities": public_entities,
        "summary": {
            "n_accounts": len(accounts),
            "n_scam_accounts": sum(a["gt_is_scam"] for a in accounts),
            "n_hijacked_accounts": len(hijacked_pairs),
            "n_normal_accounts": sum(1 - a["gt_is_scam"] for a in accounts),
            "scam_rate_actual": round(sum(a["gt_is_scam"] for a in accounts) / len(accounts), 4),
            "n_scam_rings": len(rings),
            "n_large_rings": sum(1 for r in rings if r["is_large"]),
            "n_heldout_cold_start_rings": sum(1 for r in rings if r["is_heldout"]),
            "n_benign_clusters": len(benign_clusters),
            "n_entities": len(entities),
            "n_reports": len(reports),
            "chat_verdicts_on_scam_sessions": {m: verdicts[(1, m)] for m in ("giong_chieu_lua", "chua_du_can_cu", "giong_binh_thuong")},
            "chat_verdicts_on_ordinary_sessions": {m: verdicts[(0, m)] for m in ("giong_chieu_lua", "chua_du_can_cu", "giong_binh_thuong")},
            "labels": {
                "yellow_flags_raised": sum(1 for e in label_events if e["by"] == "bao_cao_tu_dong"),
                "staff_working_days": sum(1 for c in calendar if c["working"]),
                "staff_reviews": len(staff_events),
                "staff_confirmed_scam": sum(1 for e in staff_events if e["label"] == "da_xac_nhan"),
                "staff_verified_normal": sum(1 for e in staff_events if e["label"] == "verified_normal"),
                "confirmed_scam_by_train_end": sum(
                    1 for e in staff_events if e["label"] == "da_xac_nhan" and e["day"] <= preset.train_end_day
                ),
                "verified_normal_by_train_end": sum(
                    1 for e in staff_events if e["label"] == "verified_normal" and e["day"] <= preset.train_end_day
                ),
                "still_waiting_at_end": sum(1 for lab in final_label.values() if lab == "dang_bi_bao_cao"),
                "median_days_flag_to_review": statistics.median(delays) if delays else None,
                "max_days_flag_to_review": max(delays, default=None),
            },
            "accounts_by_window": split_counts,
            "scams_by_window": scam_split,
            "entity_account_degree_by_role": {
                role: {"n": len(v), "min": min(v), "median": statistics.median(v), "max": max(v)}
                for role, v in sorted(degrees_by_role.items())
            },
            "top_20_entities_by_degree": top_hubs,
        },
    }


JSONL_TABLES = ("accounts", "entities", "reports", "label_events", "staff_calendar")


def save_dataset(data: dict[str, Any], out_dir: Path) -> Path:
    """Write the JSONL tables, `public_entities.json`, `graph_manifest.json` and `sample_preview.json`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for name in JSONL_TABLES:
        p = out_dir / f"{name}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for row in data[name]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        checksums[name] = _sha256_file(p)
    pub = out_dir / "public_entities.json"
    pub.write_text(json.dumps(data["public_entities"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checksums["public_entities"] = _sha256_file(pub)

    by_role = {}
    for a in data["accounts"]:
        by_role.setdefault(a["gt_role"], a)
    by_ent_role = {}
    for e in data["entities"]:
        by_ent_role.setdefault(e["gt_entity_role"], e)
    by_label = {}
    for e in data["label_events"]:
        by_label.setdefault(e["label"], e)
    preview = {
        "note": "A few records of each kind, for reading by eye.",
        "summary": data["summary"],
        "sample_accounts_by_role": by_role,
        "sample_entities_by_role": by_ent_role,
        "sample_reports_first_5": data["reports"][:5],
        "sample_label_events_by_label": by_label,
        "sample_staff_calendar_first_10": data["staff_calendar"][:10],
    }
    (out_dir / "sample_preview.json").write_text(
        json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest = {
        "schema_version": "e7-synth-v2",
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
    for name in JSONL_TABLES:
        with (data_dir / f"{name}.jsonl").open("r", encoding="utf-8") as f:
            out[name] = [json.loads(line) for line in f if line.strip()]
    out["public_entities"] = json.loads((data_dir / "public_entities.json").read_text(encoding="utf-8"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate one reproducible E7 mock data set (JSON / JSONL).")
    ap.add_argument("--preset", default="base", choices=sorted(PRESETS.keys()))
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out_dir = args.out or (ROOT / "data/E7" / args.preset)
    data = generate_dataset(PRESETS[args.preset], seed=args.seed)
    mp = save_dataset(data, out_dir)
    print(f"Saved {args.preset} (seed={args.seed}) -> {mp}")
    print(json.dumps(data["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
