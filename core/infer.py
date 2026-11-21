"""Scenario probabilities, next-field choice, stop rule and conclusion (design doc 5.4 and 5.5). Pure code, no model.

Likelihoods, all in log space:
- single-select field: P(v | s) from the scenario file; values the file does not list share what is left of 1 equally,
  with a floor of 0.02 (no renormalisation after the floor, as in the design doc).
- multi-select field: every value is its own yes/no variable; P(present) from the file, 0.02 if not listed.
  An answer gives the set of present values; every other value of that field counts as absent.
Empty fields and fields in `khong_chac` are skipped.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from .scenarios import Scenario
from .schema import ASKABLE, FIELDS, scored_fields

FLOOR = 0.02
STOP_TOP = 0.7
MAX_QUESTIONS = 3
DECIDE_TOP = 0.5
TIE = 0.10  # gains within 10% of the best count as a tie -> prefer a field checkable from an image


def single_dist(s: Scenario, name: str) -> dict[str, float]:
    listed = s.truong.get(name, {})
    rest = [v for v in FIELDS[name].values if v not in listed]
    share = max((1 - sum(listed.values())) / len(rest), FLOOR) if rest else 0.0
    return {v: listed.get(v, share) for v in FIELDS[name].values}


def presence(s: Scenario, name: str) -> dict[str, float]:
    listed = s.truong.get(name, {})
    return {v: listed.get(v, FLOOR) for v in FIELDS[name].values}


def log_lik(s: Scenario, name: str, value) -> float:
    if FIELDS[name].multi:
        pres, chosen = presence(s, name), set(value)
        return sum(math.log(p if v in chosen else 1 - p) for v, p in pres.items())
    return math.log(single_dist(s, name)[value])


def _normalise(logp: dict[str, float]) -> dict[str, float]:
    m = max(logp.values())
    z = sum(math.exp(x - m) for x in logp.values())
    return {k: math.exp(x - m) / z for k, x in logp.items()}


def posterior(table: dict, scen: dict[str, Scenario]) -> dict[str, float]:
    fields = scored_fields(table)
    return _normalise({sid: sum(log_lik(s, f, table[f]) for f in fields) for sid, s in scen.items()})


def entropy(p: dict[str, float]) -> float:
    return -sum(x * math.log2(x) for x in p.values() if x > 0)


def outcomes(name: str):
    f = FIELDS[name]
    if not f.multi:
        return list(f.values)
    return [list(c) for r in range(len(f.values) + 1) for c in itertools.combinations(f.values, r)]


def expected_gain(name: str, post: dict[str, float], scen: dict[str, Scenario]) -> float:
    """H(now) - E_o[H(after observing o)], with P(o) = sum_s P(s) P(o|s).
    P(o|s) of a single-select field sums to slightly over 1 because of the 0.02 floor, so the weights are divided by
    their total."""
    eh = mass = 0.0
    for o in outcomes(name):
        joint = {sid: post[sid] * math.exp(log_lik(scen[sid], name, o)) for sid in post}
        po = sum(joint.values())
        if po > 0:
            eh += po * entropy({k: v / po for k, v in joint.items()})
            mass += po
    return entropy(post) - eh / mass


def candidates(table: dict, asked: list[str]) -> list[str]:
    return [n for n in ASKABLE if n not in asked and not (table.get(n) if FIELDS[n].multi else table.get(n) is not None)
            and n not in table.get("khong_chac", [])]


def choose_field(table: dict, asked: list[str], scen: dict[str, Scenario], post=None) -> tuple[str | None, dict]:
    """Field with the highest expected entropy drop; ties (within 10%) go to an image-checkable field."""
    post = post or posterior(table, scen)
    gains = {n: expected_gain(n, post, scen) for n in candidates(table, asked)}
    if not gains:
        return None, gains
    best = max(gains, key=gains.get)
    tied = [n for n, g in gains.items() if g >= gains[best] * (1 - TIE)]
    checkable = [n for n in tied if FIELDS[n].image_checkable]
    if not FIELDS[best].image_checkable and checkable:
        best = max(checkable, key=gains.get)
    return best, gains


def should_stop(post: dict[str, float], n_asked: int) -> bool:
    return max(post.values()) >= STOP_TOP or n_asked >= MAX_QUESTIONS


@dataclass
class Conclusion:
    muc: str  # giong_chieu_lua | giong_binh_thuong | chua_du_can_cu
    top: str
    top_p: float
    phan_phoi: dict[str, float]
    dau_hieu: list[str] = field(default_factory=list)
    viec_can_kiem_tra: list[str] = field(default_factory=list)
    can_cu: list[dict] = field(default_factory=list)  # fields that pushed top over the runner-up, by log-likelihood ratio
    thieu: list[str] = field(default_factory=list)  # for chua_du_can_cu: fields still unknown that would help most


def evidence(table: dict, top: str, other: str, scen: dict[str, Scenario], k: int = 3) -> list[dict]:
    out = []
    for f in scored_fields(table):
        llr = log_lik(scen[top], f, table[f]) - log_lik(scen[other], f, table[f])
        if llr > 0:
            out.append({"truong": f, "gia_tri": table[f], "llr": round(llr, 3)})
    return sorted(out, key=lambda x: -x["llr"])[:k]


def conclude(table: dict, scen: dict[str, Scenario], asked: list[str] | None = None) -> Conclusion:
    post = posterior(table, scen)
    ranked = sorted(post, key=post.get, reverse=True)
    top, second = ranked[0], ranked[1]
    p = post[top]
    dist = {k: round(post[k], 4) for k in ranked}
    if p < DECIDE_TOP:
        _, gains = choose_field(table, asked or [], scen, post)
        missing = sorted(gains, key=gains.get, reverse=True)[:3]
        generic = ["Gọi lại cho người hoặc tổ chức qua số in trên thẻ, website chính thức, không dùng số họ đưa",
                   "Hỏi một người thân trước khi chuyển"]
        return Conclusion("chua_du_can_cu", top, p, dist, [], generic, evidence(table, top, second, scen), missing)
    s = scen[top]
    muc = "giong_chieu_lua" if s.nhom == "lua_dao" else "giong_binh_thuong"
    return Conclusion(muc, top, p, dist, list(s.dau_hieu), list(s.viec_can_kiem_tra), evidence(table, top, second, scen))
