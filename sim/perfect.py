"""Part 1 ceiling test: a "perfect answerer" (no model, no cost).

For each scenario, sample N story tables from that scenario's own probability table (fixed seed). Code-filled fields
are known from the start. The core asks; the answer is the sampled value. Same run with a random field choice.
Writes experiments/E2/perfect.json and perfect.md.

  python -m sim.perfect [--n 200] [--seed 20261121]
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from core.infer import MAX_QUESTIONS, candidates, choose_field, conclude, posterior, presence, should_stop, single_dist
from core.scenarios import ROOT, load
from core.schema import CODE_FIELDS, FIELDS, empty_table

CHUA_DU = "chua_du_can_cu"


def sample_table(s, rng: random.Random) -> dict:
    """One story table drawn field by field from the scenario's table. A multi-select draw with no value present is
    an empty list, which the core treats as unknown (same as a user who cannot say)."""
    t = {}
    for name, f in FIELDS.items():
        if f.multi:
            t[name] = [v for v, p in presence(s, name).items() if rng.random() < p]
        else:
            d = single_dist(s, name)
            t[name] = rng.choices(list(d), weights=list(d.values()))[0]
    return t


def run_session(truth: dict, scen, policy: str, rng: random.Random) -> list[dict]:
    """Returns the state after 0..MAX_QUESTIONS questions (frozen once the core stops)."""
    table = empty_table()
    for f in CODE_FIELDS:
        table[f] = truth[f]
    asked, states, stopped = [], [], False
    for k in range(MAX_QUESTIONS + 1):
        if not stopped:
            post = posterior(table, scen)
            c = conclude(table, scen, asked)
            stopped = should_stop(post, len(asked))
            snap = {"muc": c.muc, "top": c.top, "top_p": c.top_p, "n_asked": len(asked), "asked": list(asked)}
        states.append(snap)
        if stopped:
            continue
        if policy == "entropy":
            f, _ = choose_field(table, asked, scen, post)
        else:
            cand = candidates(table, asked)
            f = rng.choice(cand) if cand else None
        if f is None:
            stopped = True
            continue
        asked.append(f)
        table[f] = truth[f]
    return states


def predicted(st) -> str:
    return CHUA_DU if st["muc"] == CHUA_DU else st["top"]


def run(n: int, seed: int):
    scen, issues = load()
    res = {}
    for policy in ("entropy", "random"):
        rows = []
        for sid in sorted(scen):
            rng = random.Random(f"{seed}:{sid}")  # same tables for both policies
            prng = random.Random(f"{seed}:{sid}:policy")
            for i in range(n):
                truth = sample_table(scen[sid], rng)
                rows.append({"truth": sid, "nhom": scen[sid].nhom, "i": i,
                             "states": run_session(truth, scen, policy, prng)})
        res[policy] = rows
    return scen, issues, res


def summarise(scen, rows):
    out = {}
    for k in range(MAX_QUESTIONS + 1):
        c = Counter()
        for r in rows:
            st = r["states"][k]
            pred = predicted(st)
            c["n"] += 1
            c["dung_kb"] += pred == r["truth"]
            c["chua_du"] += pred == CHUA_DU
            c["dung_nhom"] += pred != CHUA_DU and scen[pred].nhom == r["nhom"]
        out[k] = c
    return out


def pct(a, b):
    return f"{100 * a / b:.1f}" if b else "-"


def report(scen, issues, res, n, seed, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    L = [f"### Phần 1: người trả lời hoàn hảo ({n} bảng mỗi kịch bản, seed {seed})\n",
         f"{len(scen)} kịch bản nạp được ({sum(s.nhom == 'lua_dao' for s in scen.values())} lừa đảo, "
         f"{sum(s.nhom == 'binh_thuong' for s in scen.values())} bình thường); {len(res['entropy'])} phiên mỗi cách chọn. "
         "Mỗi bảng lấy mẫu từng trường theo đúng bảng xác suất của kịch bản đó; 4 trường do code điền biết từ đầu; "
         "người dùng trả lời đúng giá trị đã lấy mẫu. Sau k câu = trạng thái sau k câu, hoặc lúc dừng nếu đã dừng sớm "
         "(xác suất đứng đầu >= 0,7). Mẫu số là mọi phiên; phiên \"chưa đủ căn cứ\" tính là không đúng kịch bản và "
         "không đúng nhóm; đúng nhóm gồm cả đúng kịch bản.\n"]
    if issues:
        L.append("File kịch bản bị bỏ vì lỗi (không tự sửa): " + "; ".join(f"`{i}`".replace("\n", " ") for i in issues) + "\n")
    L.append("| Cách chọn trường | Sau k câu | Đúng kịch bản | Đúng nhóm | Chưa đủ căn cứ |")
    L.append("|---|---|---|---|---|")
    summ = {p: summarise(scen, rows) for p, rows in res.items()}
    for p in ("entropy", "random"):
        for k, c in summ[p].items():
            L.append(f"| {'entropy' if p == 'entropy' else 'ngẫu nhiên'} | {k} | {pct(c['dung_kb'], c['n'])}% | "
                     f"{pct(c['dung_nhom'], c['n'])}% | {pct(c['chua_du'], c['n'])}% |")
    ent = res["entropy"]
    qs = [r["states"][-1]["n_asked"] for r in ent]
    L.append(f"\nSố câu hỏi trung bình trước khi dừng (entropy): {sum(qs) / len(qs):.2f}; "
             f"ngẫu nhiên: {sum(r['states'][-1]['n_asked'] for r in res['random']) / len(res['random']):.2f}.\n")

    # Normal scenarios concluded as scam (E3 ceiling), and the hard-to-tell normal one
    L.append("**Theo kịch bản, sau 3 câu (entropy):**\n")
    L.append("| Kịch bản | Nhóm | Đúng kịch bản | Đúng nhóm | Chưa đủ căn cứ | Kết luận \"giống chiêu lừa\" | Mong đợi |")
    L.append("|---|---|---|---|---|---|---|")
    per = defaultdict(list)
    for r in ent:
        per[r["truth"]].append(r)
    fp_num = fp_den = 0
    for sid in sorted(per, key=lambda x: (scen[x].nhom, x)):
        rs = per[sid]
        preds = [predicted(r["states"][-1]) for r in rs]
        scam = sum(p != CHUA_DU and scen[p].nhom == "lua_dao" for p in preds)
        if scen[sid].nhom == "binh_thuong":
            fp_num += scam
            fp_den += len(rs)
        expect = ("chưa đủ căn cứ" if scen[sid].kho_phan_biet_voi else
                  "giống chiêu lừa" if scen[sid].nhom == "lua_dao" else "giống bình thường")
        L.append(f"| `{sid}` | {scen[sid].nhom} | {pct(sum(p == sid for p in preds), len(rs))}% | "
                 f"{pct(sum(p != CHUA_DU and scen[p].nhom == scen[sid].nhom for p in preds), len(rs))}% | "
                 f"{pct(preds.count(CHUA_DU), len(rs))}% | {pct(scam, len(rs))}% | {expect} |")
    L.append(f"\nKịch bản bình thường bị kết luận \"giống chiêu lừa\" (trần E3): {pct(fp_num, fp_den)}% "
             f"({fp_num}/{fp_den}).\n")

    # Confusion
    conf = Counter((r["truth"], predicted(r["states"][-1])) for r in ent)
    off = sorted(((c, t, p) for (t, p), c in conf.items() if t != p and p != CHUA_DU), reverse=True)
    L.append("**Cặp nhầm nhiều nhất (đáp án → kết luận, sau 3 câu, entropy):**\n")
    for c, t, p in off[:8]:
        L.append(f"- `{t}` → `{p}`: {c}/{len(per[t])} ({pct(c, len(per[t]))}%)")
    ids = sorted(scen, key=lambda x: (scen[x].nhom, x))
    short = {sid: f"{i + 1}" for i, sid in enumerate(ids)}
    L.append("\nMa trận nhầm (hàng: đáp án, cột: kết luận; số cột theo thứ tự hàng; `?` = chưa đủ căn cứ):\n")
    L.append("| Đáp án | " + " | ".join(short[s] for s in ids) + " | ? |")
    L.append("|---|" + "---|" * (len(ids) + 1))
    for t in ids:
        L.append(f"| {short[t]} `{t}` | " + " | ".join(str(conf.get((t, p), "")) for p in ids)
                 + f" | {conf.get((t, CHUA_DU), '')} |")
    md = "\n".join(L) + "\n"
    (out_dir / "perfect.md").write_text(md, encoding="utf-8")
    js = {p: {str(k): dict(c) for k, c in s.items()} for p, s in summ.items()}
    (out_dir / "perfect.json").write_text(json.dumps({"n": n, "seed": seed, "summary": js, "issues": [str(i) for i in issues],
                                                     "confusion": {f"{t}|{p}": c for (t, p), c in conf.items()}},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return summ, md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261121)
    ap.add_argument("--out", default=str(ROOT / "experiments/E2"))
    a = ap.parse_args()
    scen, issues, res = run(a.n, a.seed)
    _, md = report(scen, issues, res, a.n, a.seed, Path(a.out))
    print(md)


if __name__ == "__main__":
    main()
