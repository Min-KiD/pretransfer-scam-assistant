"""T4 report: catalogue v2 stories and C0 retrained on 25 scenarios -> experiments/T4/report.md (English).

  uv run --no-project --with-requirements requirements.txt --with numpy --with tokenizers python -m e6.t4_report

Reads data/E6/cases.jsonl, data/E6/cost.json and data/E6/v2/cost_before_t4.json (copied before the story run),
C0 v1 predictions data/E6/preds/c0.jsonl (15 labels), C0 v2 predictions data/E6/v2/preds/c0.jsonl (25 labels), the 300
v1 cases and the real narratives. Token counts use the Qwen3-4B-Instruct-2507 tokenizer file in .cache/t4/ (local, no
API). No model calls.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict

from core.scenarios import ROOT, load
from e6.classify import DATA, SCEN, SCEN_V2, train_val
from sim.cases import CASE_DIR
from sim.e10_d import mcnemar_p
from sim.e5 import fmt, rate
from sim.run import CHUA_DU, FREE_PROMPT, account_line, bootstrap, history_text

OUT = ROOT / "experiments/T4"
TOKENIZER = ROOT / ".cache/t4/qwen3-4b-instruct-2507-tokenizer.json"
NEW = [s for s in SCEN_V2 if s not in SCEN]
KINDS = ("mo_dau", "day_du")
STORIES_PER_SCENARIO = 5


def load_preds(path, labels):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    for r in rows:
        p = r["probs"]
        i = max(range(len(p)), key=p.__getitem__)
        r["top"], r["conf"] = labels[i], p[i]
        r["p_label"] = p[labels.index(r["label"])] if r["label"] in labels else None
    return rows


def acc(rows):
    return fmt(rate(sum(r["top"] == r["label"] for r in rows), len(rows)))


def cross(rows, nhom, a, b):
    """Rows of group a answered with a scenario of group b."""
    rs = [r for r in rows if nhom.get(r["label"]) == a]
    return fmt(rate(sum(nhom[r["top"]] == b for r in rs), len(rs)))


def paired(a, b):
    """a, b: {key: correct}; on common keys -> n, a acc, b acc, diff [bootstrap 95%], McNemar p."""
    keys = sorted(set(a) & set(b))
    d = [float(a[k]) - float(b[k]) for k in keys]
    lo, hi = bootstrap(d)
    ab = sum(a[k] and not b[k] for k in keys)
    ba = sum(b[k] and not a[k] for k in keys)
    return (len(keys), sum(a[k] for k in keys), sum(b[k] for k in keys), 100 * sum(d) / len(d), 100 * lo, 100 * hi,
            mcnemar_p(ab, ba))


def turn0_prompt(case, scen, ids):
    catalog = "\n".join(f"- {s}: {scen[s].ten} - {scen[s].mo_ta}" for s in ids)
    instr = "Nếu đã đủ chắc thì dừng (cau_hoi rỗng), nếu chưa thì hỏi một câu giúp phân biệt các kịch bản."
    prompt = FREE_PROMPT.format(catalog=catalog, chua_du=CHUA_DU, account=account_line(case), asked=0,
                                instruction=instr, history=history_text([{"role": "user",
                                                                           "text": case["tin_mo_dau"]}]),
                                image_block="")
    return catalog, prompt


def main():
    scen, issues = load()
    assert not issues, issues
    nhom = {s: scen[s].nhom for s in SCEN_V2}
    rows = [json.loads(l) for l in open(DATA / "cases.jsonl", encoding="utf-8")]
    cost = json.loads((DATA / "cost.json").read_text())
    before_p = DATA / "v2/cost_before_t4.json"
    before = json.loads(before_p.read_text()) if before_p.exists() else None
    meta = json.loads((DATA / "v2/models.json").read_text()).get("c0", {})
    v2 = load_preds(DATA / "v2/preds/c0.jsonl", SCEN_V2)
    v1 = load_preds(DATA / "preds/c0.jsonl", SCEN)
    _, _, dropped = train_val("v2")

    L = ["# T4 - Catalogue v2: 25 scenarios, cleaner case generator, C0 retrained\n",
         "Brief: `docs/tasks/T4-catalogue-v2.md`. Go: Minh, 2026-11-26. Report: `python -m e6.t4_report` (command in its "
         "docstring). Rates as k/n [Wilson 95%].\n"]
    if before:
        L.append(f"**Spend (recorded): {cost['usd'] - before['usd']:.4f} USD** (`gemini-3.5-flash-lite`, "
                 f"{cost['calls'] - before['calls']} calls, stories of step 4); cap 1.0 USD. No other provider, no "
                 "server, no GPU.\n")
    else:
        L.append("**Spend: not recorded** (`data/E6/v2/cost_before_t4.json` missing).\n")

    # ---- stories and the rule
    L += ["## Stories and rows dropped by the rule\n",
          "Stories for the 10 new scenarios were appended to `data/E6/cases.jsonl` (existing rows untouched), batches "
          "interleaved across scenarios. Rows dropped from C0 v2 training: ordinary rows whose story table carries a "
          "scam-type detail (`sim.cases.scam_details`, the rule the generator now applies).\n",
          "| Scenario | Group | Train rows | Val rows | Dropped (train / val) |", "|---|---|---|---|---|"]
    by_sid = defaultdict(Counter)
    for r in rows:
        by_sid[r["kich_ban"]][r["split"]] += 1
    drop_by = defaultdict(Counter)
    for split, ids in dropped.items():
        for i in ids:
            drop_by[i[3:].rsplit("__", 1)[0]][split] += 1
    for s in SCEN_V2:
        if s in NEW or drop_by[s]:
            L.append(f"| `{s}`{' (new)' if s in NEW else ''} | {nhom[s]} | {by_sid[s]['train']} | {by_sid[s]['val']} | "
                     f"{drop_by[s]['train']} / {drop_by[s]['val']} |")
    n_ord = sum(1 for r in rows if r["nhom"] == "binh_thuong" and r["kich_ban"] in SCEN)
    L.append(f"\nDropped in total: {len(dropped['train']) + len(dropped['val'])} of {n_ord} v1 ordinary rows "
             f"(train {len(dropped['train'])}, val {len(dropped['val'])}); new ordinary rows dropped: "
             f"{sum(drop_by[s]['train'] + drop_by[s]['val'] for s in NEW)} (the generator already applies the rule). "
             f"C0 v2: C={meta.get('train', {}).get('C')} (the smallest value of the E6 grid 1, 4, 16, 64, as for C0 "
             f"v1), val macro-F1 {meta.get('train', {}).get('val_macro_f1')}, {meta.get('train_n')} train and "
             f"{meta.get('val_n')} val inputs (two per row), CPU {meta.get('cpu_ms_p50')} ms per text (p50), "
             f"{meta.get('size_mb')} MB.\n")

    # ---- C0 v2 on val
    val2 = [r for r in v2 if r["set"] == "val"]
    L += ["## C0 v2 on val\n",
          "| Input | Correct scenario | Scam called ordinary | Ordinary called scam |", "|---|---|---|---|"]
    for k in KINDS:
        rs = [r for r in val2 if r["kind"] == k]
        L.append(f"| `{k}` | {acc(rs)} | {cross(rs, nhom, 'lua_dao', 'binh_thuong')} | "
                 f"{cross(rs, nhom, 'binh_thuong', 'lua_dao')} |")
    L += ["\nPer scenario (correct scenario):\n", "| Scenario | Group | `mo_dau` | `day_du` |", "|---|---|---|---|"]
    for s in SCEN_V2:
        cells = [acc([r for r in val2 if r["kind"] == k and r["label"] == s]) for k in KINDS]
        L.append(f"| `{s}`{' (new)' if s in NEW else ''} | {nhom[s]} | " + " | ".join(cells) + " |")

    # ---- v1 vs v2 on the 15 old scenarios
    L += ["\n## C0 v1 against C0 v2 on the val rows of the 15 v1 scenarios\n",
          "Same inputs (val rows of the v1 scenarios that the rule keeps). v1 chooses among 15 scenarios, v2 among 25; a v2 "
          "answer naming a new scenario counts as wrong. Difference v2 - v1 with a paired bootstrap 95% interval; exact "
          "McNemar.\n",
          "| Input | n | C0 v1 | C0 v2 | v2 - v1 | McNemar p | v2 answers a new scenario |", "|---|---|---|---|---|---|---|"]
    for k in KINDS:
        a = {r["id"]: r["top"] == r["label"] for r in val2 if r["kind"] == k and r["label"] in SCEN}
        b = {r["id"]: r["top"] == r["label"] for r in v1 if r["set"] == "val" and r["kind"] == k}
        n, ka, kb, d, lo, hi, p = paired(a, b)
        new_ans = sum(r["top"] in NEW for r in val2 if r["kind"] == k and r["label"] in SCEN)
        L.append(f"| `{k}` | {n} | {fmt(rate(kb, n))} | {fmt(rate(ka, n))} | {d:+.1f} [{lo:+.1f}, {hi:+.1f}] | {p:.3f} | "
                 f"{fmt(rate(new_ans, n))} |")

    # ---- confusion
    conf = Counter((r["label"], r["top"]) for r in val2 if r["label"] != r["top"])
    tot = Counter(r["label"] for r in val2)
    L += ["\n## Confusion on val (both inputs pooled)\n",
          "The 10 largest true -> answered pairs (share of that scenario's val inputs).\n",
          "| True | Answered | Inputs | Share | Group changes |", "|---|---|---|---|---|"]
    for (t, p), c in conf.most_common(10):
        L.append(f"| `{t}` | `{p}` | {c} | {100 * c / tot[t]:.1f}% | {'yes' if nhom[t] != nhom[p] else 'no'} |")
    pairs = [("mo_vi_tra_sau_nhan_hoa_hong", "ctv_online")]
    for s in NEW:
        ref = scen[s].raw.get("doi_chieu_voi")
        if nhom[s] == "binh_thuong" and ref:
            pairs += [(s, x) for x in ([ref] if isinstance(ref, str) else ref)]
    L += ["\nNamed pairs (pay-later scam and `ctv_online`; each new ordinary scenario and the scam in its "
          "`doi_chieu_voi`), both directions:\n",
          "| A | B | A answered B | B answered A |", "|---|---|---|---|"]
    for x, y in pairs:
        L.append(f"| `{x}` | `{y}` | {conf[(x, y)]}/{tot[x]} | {conf[(y, x)]}/{tot[y]} |")

    # ---- real narratives
    real2 = {r["id"]: r for r in v2 if r["set"] == "real"}
    real1 = {r["id"]: r for r in v1 if r["set"] == "real"}
    narr = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data/narr/real").glob("*.json"))}
    labelled = [r for r in real2.values() if r["label"] != "khac"]
    relab = [i for i in real2 if real1[i]["label"] == "khac" and real2[i]["label"] != "khac"]
    old = [i for i in real2 if real1[i]["label"] != "khac"]
    o1, o2 = [real1[i] for i in old], [real2[i] for i in old]
    L += ["\n## Real narratives\n",
          f"C0 v2 on the {len(labelled)} labelled narratives (all scams): correct scenario {acc(labelled)}; called "
          f"ordinary {cross(labelled, nhom, 'lua_dao', 'binh_thuong')}. On the {len(old)} narratives labelled in v1: "
          f"correct scenario C0 v1 {acc(o1)}, C0 v2 {acc(o2)}; called ordinary C0 v1 "
          f"{cross(o1, nhom, 'lua_dao', 'binh_thuong')}, C0 v2 {cross(o2, nhom, 'lua_dao', 'binh_thuong')}.\n",
          "C0 v2 answers on the labelled narratives it calls ordinary: "
          + ", ".join(f"`{s}` {c}" for s, c in Counter(r["top"] for r in labelled
                                                        if nhom[r["top"]] == "binh_thuong").most_common()) + ".\n",
          "The relabelled narratives:\n", "| Narrative | New label | C0 v2 answer | p(answer) | p(label) | Label rank |",
          "|---|---|---|---|---|---|"]
    for i in sorted(relab):
        r = real2[i]
        rank = 1 + sum(p > r["p_label"] for p in r["probs"])
        L.append(f"| `{narr_id(narr, i)}` | `{r['label']}` | `{r['top']}` | {r['conf']:.2f} | {r['p_label']:.2f} | {rank} |")
    L += ["\nThe narratives that stay `khac` (outside the catalogue):\n", "| Narrative | C0 v2 answer | Group | p(answer) |",
          "|---|---|---|---|"]
    for i in sorted(i for i, r in real2.items() if r["label"] == "khac"):
        r = real2[i]
        L.append(f"| `{narr_id(narr, i)}` | `{r['top']}` | {nhom[r['top']]} | {r['conf']:.2f} |")

    # ---- 300 v1 openings
    sim2 = {r["id"]: r for r in v2 if r["set"] == "sim"}
    sim1 = {r["id"]: r for r in v1 if r["set"] == "sim"}
    n, k2, k1, d, lo, hi, p = paired({i: r["top"] == r["label"] for i, r in sim2.items()},
                                     {i: r["top"] == r["label"] for i, r in sim1.items()})
    s1, s2 = list(sim1.values()), list(sim2.values())
    L += ["\n## The openings of the 300 v1 cases\n",
          "| Model | Correct scenario | Scam called ordinary | Ordinary called scam | Answers a new scenario |",
          "|---|---|---|---|---|",
          f"| C0 v1 (15) | {fmt(rate(k1, n))} | {cross(s1, nhom, 'lua_dao', 'binh_thuong')} | "
          f"{cross(s1, nhom, 'binh_thuong', 'lua_dao')} | - |",
          f"| C0 v2 (25) | {fmt(rate(k2, n))} | {cross(s2, nhom, 'lua_dao', 'binh_thuong')} | "
          f"{cross(s2, nhom, 'binh_thuong', 'lua_dao')} | {fmt(rate(sum(r['top'] in NEW for r in s2), n))} |",
          f"\nv2 - v1: {d:+.1f} points [{lo:+.1f}, {hi:+.1f}], McNemar p={p:.3f}. These cases were drawn with the v1 "
          "generator (account label at random, no rule), so they still carry the noise of data plan v2, section 3.7.\n"]

    # ---- chat prompt tokens
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(TOKENIZER))
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASE_DIR.glob("*.json"))]
    ntok = lambda t: len(tok.encode(t).ids)  # noqa: E731
    res = {}
    for name, ids in (("15 (v1)", SCEN), ("25 (v2)", SCEN_V2)):
        cat = ntok(turn0_prompt(cases[0], scen, ids)[0])
        full = [ntok(turn0_prompt(c, scen, ids)[1]) for c in cases]
        res[name] = (cat, sum(full) / len(full), max(full))
    L += ["## Chat prompt of `sim/run.py::run_tu_do`\n",
          f"Tokens counted with the Qwen3-4B-Instruct-2507 tokenizer (local file). First turn (no question asked yet) "
          f"over the {len(cases)} v1 cases; later turns add the dialogue, and the catalogue block is the same in every "
          "turn, so the difference below is paid on every call. The schema `enum` grows by 10 ids as well (not counted).\n",
          "| Catalogue | Catalogue block | Prompt, first turn (mean) | Max |", "|---|---|---|---|"]
    for name, (cat, mean, mx) in res.items():
        L.append(f"| {name} scenarios | {cat} | {mean:.0f} | {mx} |")
    (c1, m1, _), (c2, m2, _) = res.values()
    L.append(f"\nPer turn: +{c2 - c1} tokens (+{100 * (m2 - m1) / m1:.0f}% of the first-turn prompt).\n")

    # ---- sample stories
    L += ["## Five stories per new scenario (seeded draw)\n",
          f"Drawn with `random.Random('T4:<scenario>')` from that scenario's rows. Persona, account label (not shown to "
          "the writer), opening, then the three questions and answers.\n"]
    for s in NEW:
        rs = sorted((r for r in rows if r["kich_ban"] == s), key=lambda r: int(r["id"].rsplit("__", 1)[1]))
        L.append(f"### `{s}` ({nhom[s]}): {scen[s].ten}\n")
        for r in random.Random(f"T4:{s}").sample(rs, min(STORIES_PER_SCENARIO, len(rs))):
            L.append(f"- `{r['id']}` ({r['split']}, {r['tinh_cach']}, account `{r['bang_that']['nhan_tai_khoan']}`): "
                     f"{r['tin_mo_dau']}")
            for q, ans in zip(r["cau_hoi"], r["tra_loi"]):
                L.append(f"  - *{q}* {ans}")
        L.append("")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("report:", (OUT / "report.md").relative_to(ROOT))


def narr_id(narr, i):
    return narr[i]["id"] if i in narr else i


if __name__ == "__main__":
    main()
