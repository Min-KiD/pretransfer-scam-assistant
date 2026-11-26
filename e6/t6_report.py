"""T6 report: test set v2 (sim/cases_v2/, written by GPT) and the flash-lite baseline -> experiments/T6/report.md.

  python3 -m e6.t6_report          (anaconda python: the C0 classifiers need sklearn)

Inputs: sim/cases_v2/ (part A, `python -m sim.t6_cases`), experiments/T6/sessions.jsonl (part C,
`python -m sim.e5 --cases sim/cases_v2 --out experiments/T6 --order-seed 20261128 --models gemini-3.5-flash-lite
--cap-usd 1.0 --project-after 50`), the C0 v2 and v3 weights in .cache/e6/{v2,v3}/c0 and their val predictions in
data/E6/{v2,v3}/preds/c0.jsonl. The v1 figures are the E5 flash-lite sessions (experiments/E5/sessions.jsonl).

Second opinion, scored as in the E6 report (e6/report.py): the classifier reads the user's own words of the session
(`day_du`); "disagree" = its top scenario differs from the LLM's conclusion after 3 questions, either at any
confidence or only above tau (smallest of 0.30..0.95 at which the classifier is right on >= 95% of its own val inputs
above tau). Applied rule: disagree -> `chua_du_can_cu`. M3: catches >= 30% of the wrong conclusions and flags <= 15%
of the right ones. Sessions the LLM ends in `chua_du_can_cu` are left out of the M3 counts.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict

from core.scenarios import ROOT, load
from e6.classify import SCEN, SCEN_V2, WDIR, c0_predict
from e6.report import pick_tau
from sim.e5 import BASE, K, confusions, fmt, load_cases, load_rows, per_scenario, rate, score
from sim.run import CHUA_DU
from sim.t6_cases import A2_CORES

CASES = ROOT / "sim/cases_v2"
OUT = ROOT / "experiments/T6"
NEW = [s for s in SCEN_V2 if s not in SCEN]
SEED = 20261128
CLS = {"C0 v2 (T4)": ("v2", WDIR / "v2/c0"), "C0 v3 (T4b)": ("v3", WDIR / "v3/c0")}


def norm(t):
    return " ".join(t.lower().split())


def tag(s):
    return f"`{s}`" + (" (new)" if s in NEW else "")


def account(c):
    return c.get("tai_khoan", {}).get("nhan_tai_khoan", "?")


def identical_openings(cases):
    """Openings of cases_v2 equal (lower-case, collapsed spaces) to an opening of the train data or of v1, or to
    another case of the set."""
    old = {}
    for name in ("cases.jsonl", "cases_v2.jsonl"):
        for l in open(ROOT / "data/E6" / name, encoding="utf-8"):
            r = json.loads(l)
            old.setdefault(norm(r["tin_mo_dau"]), f"data/E6/{name}:{r['id']}")
    for p in sorted((ROOT / "sim/cases").glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        old.setdefault(norm(c["tin_mo_dau"]), f"sim/cases:{c['id']}")
    hits, seen = [], {}
    for c in cases:
        t = norm(c["tin_mo_dau"])
        if t in old:
            hits.append((c["id"], old[t]))
        if t in seen:
            hits.append((c["id"], f"sim/cases_v2:{seen[t]}"))
        seen.setdefault(t, c["id"])
    return len(old), hits


def metric_rows(S):
    return (f"{fmt(S['kb0'])} | {fmt(S['kb1'])} | {fmt(S['kb2'])} | {fmt(S['kb3'])} | {fmt(S['miss'])} | "
            f"{fmt(S['fp'])} | {fmt(S['chua_du'])} | {S['q']:.2f} | {S['sec_mean']:.2f} | "
            f"{S['usd'] + S['victim_usd'] / S['n']:.5f}")


HEAD = ("| Set | Sessions | Correct after 0 q | after 1 | after 2 | after 3 | Scam called ordinary | Ordinary flagged as "
        f"scam | `{CHUA_DU}` | Questions | Seconds per call | USD per session |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|")


def second_opinion(L, name, labels, model_dir, val_path, sess, scen):
    nhom = {s: scen[s].nhom for s in SCEN_V2}
    val = [json.loads(l) for l in open(val_path, encoding="utf-8")]
    val = [r for r in val if r["set"] == "val"]
    for r in val:
        i = max(range(len(r["probs"])), key=r["probs"].__getitem__)
        r["top"], r["conf"] = labels[i], r["probs"][i]
    tau = pick_tau(val)
    texts = [" ".join(h["text"] for h in r["history"] if h["role"] == "user") for r in sess]
    probs, _ = c0_predict(texts, model_dir)
    cl = {}
    for r, p in zip(sess, probs):
        i = int(p.argmax())
        cl[r["case"]] = {"top": labels[i], "conf": float(p[i])}
    n_all = len(sess)
    concl = [r for r in sess if r["preds"][K] != CHUA_DU]
    n_chua = n_all - len(concl)
    wrong = [r for r in concl if r["preds"][K] != r["kich_ban"]]
    right = [r for r in concl if r["preds"][K] == r["kich_ban"]]
    L += [f"### {name} behind flash-lite\n",
          f"tau = {tau} (from this classifier's own val predictions, `{val_path.relative_to(ROOT)}`). "
          f"{n_chua} of {n_all} sessions end in `{CHUA_DU}` and are left out of the M3 counts.\n",
          "| Rule | LLM right, classifier disagrees | LLM wrong, classifier disagrees | M3 (catch >= 30%, flag <= 15%) |",
          "|---|---|---|---|"]
    rules = (("disagree at any confidence", lambda c, x: c["top"] != x),
             (f"disagree with top probability > {tau}", lambda c, x: c["top"] != x and c["conf"] > tau))
    outcomes = [("No second opinion", None)]
    for rule, dis in rules:
        fr = sum(dis(cl[r["case"]], r["preds"][K]) for r in right)
        cw = sum(dis(cl[r["case"]], r["preds"][K]) for r in wrong)
        ok = bool(wrong) and cw / len(wrong) >= 0.30 and (not right or fr / len(right) <= 0.15)
        L.append(f"| {rule} | {fmt(rate(fr, len(right)))} | {fmt(rate(cw, len(wrong)))} | "
                 f"**{'met' if ok else 'not met'}** |")
        outcomes.append((f"Disagree ({rule.split(' ', 2)[2] if ' > ' in rule else 'any confidence'}) -> "
                         f"`{CHUA_DU}`", dis))
    L += ["\nThe rows of the main table with the rule applied (a demoted session counts as `chua_du_can_cu`: not "
          "correct, not a false alarm, not a miss):\n",
          f"| Rule | Correct after 3 q | Correct among sessions still concluded | Scam called ordinary | Ordinary "
          f"flagged as scam | `{CHUA_DU}` |", "|---|---|---|---|---|---|"]
    scam = [r for r in sess if r["nhom"] == "lua_dao"]
    normal = [r for r in sess if r["nhom"] == "binh_thuong"]
    for title, dis in outcomes:
        final = {r["case"]: (CHUA_DU if dis and r["preds"][K] != CHUA_DU and dis(cl[r["case"]], r["preds"][K])
                             else r["preds"][K]) for r in sess}
        kept = [r for r in sess if final[r["case"]] != CHUA_DU]
        L.append(f"| {title} | {fmt(rate(sum(final[r['case']] == r['kich_ban'] for r in sess), n_all))} | "
                 f"{fmt(rate(sum(final[r['case']] == r['kich_ban'] for r in kept), len(kept)))} | "
                 f"{fmt(rate(sum(final[r['case']] != CHUA_DU and nhom[final[r['case']]] == 'binh_thuong' for r in scam), len(scam)))} | "
                 f"{fmt(rate(sum(final[r['case']] != CHUA_DU and nhom[final[r['case']]] == 'lua_dao' for r in normal), len(normal)))} | "
                 f"{fmt(rate(n_all - len(kept), n_all))} |")
    L.append("")


def alone(name, labels, model_dir, cases, scen):
    nhom = {s: scen[s].nhom for s in SCEN_V2}
    probs, _ = c0_predict([c["tin_mo_dau"] for c in cases], model_dir)
    top = [labels[int(p.argmax())] for p in probs]
    scam = [(c, t) for c, t in zip(cases, top) if c["nhom"] == "lua_dao"]
    normal = [(c, t) for c, t in zip(cases, top) if c["nhom"] == "binh_thuong"]
    newc = [(c, t) for c, t in zip(cases, top) if c["kich_ban"] in NEW]
    return (f"| {name} | {fmt(rate(sum(t == c['kich_ban'] for c, t in zip(cases, top)), len(cases)))} | "
            f"{fmt(rate(sum(nhom[t] == 'binh_thuong' for _, t in scam), len(scam)))} | "
            f"{fmt(rate(sum(nhom[t] == 'lua_dao' for _, t in normal), len(normal)))} | "
            f"{fmt(rate(sum(t == c['kich_ban'] for c, t in newc), len(newc)))} |")


def main():
    scen, issues = load()
    assert not issues, issues
    nhom = {s: scen[s].nhom for s in SCEN_V2}
    cases = load_cases(CASES)
    by_id = {c["id"]: c for c in cases}
    viec = json.loads((CASES / "_viec.json").read_text(encoding="utf-8"))
    dropped = json.loads((CASES / "_dropped.json").read_text(encoding="utf-8")) if (CASES / "_dropped.json").exists() else []
    cost = json.loads((CASES / "_cost.json").read_text(encoding="utf-8"))
    sess = [r for r in load_rows(OUT / "sessions.jsonl") if "preds" in r and r["model"] == BASE]
    old_sess = [r for r in load_rows(OUT / "sessions_replaced.jsonl") if "preds" in r and r["model"] == BASE]
    a2_ids = {c["id"] for c in cases if c.get("a2")}
    vc = re.search(r"(\d+) calls, ([\d.]+) USD", (OUT / "victim_check.md").read_text(encoding="utf-8"))
    vc_usd = float(vc.group(2)) if vc else 0.0
    gem = sum(r["usd"] + r.get("victim_usd", 0) for r in sess + old_sess)

    L = ["# T6 - Test set v2 (written by GPT) and the flash-lite baseline\n",
         "Brief: `docs/tasks/T6-test-set-v2.md`. Report: `python3 -m e6.t6_report`. Rates as k/n [Wilson 95%]; one run per "
         "configuration.\n",
         "## Spend\n",
         "| Provider | Part | USD | Cap |", "|---|---|---|---|",
         f"| OpenAI (`gpt-6.2-sol`) | A and A2: purpose lines, openings, re-reads ({cost['calls']} calls) | "
         f"{cost['usd']:.4f} | 1.6 (1.5 before A2) |",
         f"| Gemini (`gemini-3.5-flash-lite`) | B2: simulated-user check (120 calls) | {vc_usd:.4f} | - |",
         f"| Gemini (`gemini-3.5-flash-lite`) | C: {len(sess)} sessions + {len(old_sess)} on the cases replaced by A2, "
         f"assistant + simulated user | {gem:.4f} | 1.0 |",
         "\nNo server, no GPU.\n"]

    # ---------------------------------------------------------------- part A
    per = defaultdict(Counter)
    for c in cases:
        per[c["kich_ban"]][f"vong{c.get('vong', 0)}"] += 1
    drop = Counter(d["kich_ban"] for d in dropped)
    rejected = sum(len(v["rejected_train"]) for v in viec.values())
    dups = sum(len(v["duplicates"]) for v in viec.values())
    n_old, hits = identical_openings(cases)
    L += ["## Part A - Cases\n",
          f"{len(cases)} cases in `sim/cases_v2/` (`<scenario>__<i>.json`, same keys as v1 plus `viec`, `sinh_boi`, "
          f"`vong`, and `doc_lai` on ordinary cases). Tables from `sim.cases.make_case` with "
          f"`random.Random('{SEED}:<scenario>:cases_v2')`; personas in rotation; opening by `openai:gpt-6.2-sol` with "
          "`OPENING_PROMPT` as left by T4b. Jobs ran round-robin over the 25 scenarios in chunks of 25.\n",
          f"- Purpose lines: one call per scenario ({len(viec)} calls) asked for N + 10 lines given `ten`, `mo_ta`, "
          f"`cac_buoc` and the train lines of `sim/viec_dang_lam.yaml` as \"do not reuse\". "
          f"{sum(len(v['lines']) for v in viec.values())} lines kept; **{rejected} rejected** as equal to a train line "
          f"(lower-case, stripped); {dups} dropped as duplicates within the scenario. Each case uses a different line.",
          "- Re-read of ordinary openings: **batched**, one `gpt-6.2-sol` call per chunk for that chunk's ordinary openings "
          "(numbered), with the catalogue lines of the 15 scam scenarios; answer per message `mau_thuan`, `kich_ban`, "
          "`ly_do`. The brief has one call per message; batching was my change, because single re-reads projected about "
          "2.2 USD against the 1.5 cap (the catalogue block is about 6.8k characters). The prompt also says that a shared "
          "general topic (a deposit, paying a shipper, sending to family) is not enough to flag a message; it needs a "
          "detail that the scam type describes (my wording).",
          f"- **Part A2** (planner, after reading part A): the purpose lines of `{'`, `'.join(sorted(A2_CORES))}` had "
          "drifted off their subject (the prompt forbade paraphrasing the train lines, and these scams have one purpose "
          f"only). Their {len(a2_ids)} cases got new purpose lines (`VIEC_PROMPT_A2`: \"do not copy\" plus a core purpose "
          "given verbatim by the brief) and new openings; tables, personas and ids unchanged. Old files in "
          "`sim/cases_v2/_replaced/`, old and new side by side in `experiments/T6/a2.md`.",
          f"- Identical openings (lower-case, spaces collapsed) against {n_old} openings of `data/E6/cases.jsonl`, "
          f"`data/E6/cases_v2.jsonl` and `sim/cases/`, and within the set: **{len(hits)}**"
          + (": " + ", ".join(f"`{a}` = `{b}`" for a, b in hits) if hits else "") + ".\n",
          "| Scenario | Group | Kept | Of which replacements | Dropped by the re-read | Dropped share |",
          "|---|---|---|---|---|---|"]
    for s in SCEN_V2:
        kept = sum(per[s].values())
        rep = kept - per[s]["vong0"]
        L.append(f"| {tag(s)} | {nhom[s]} | {kept} | {rep} | {drop[s]} | "
                 f"{f'{100 * drop[s] / (kept + drop[s]):.0f}%' if nhom[s] == 'binh_thuong' else 'not filtered'} |")
    L.append(f"\nTotal: {len(cases)} kept ({sum(c['nhom'] == 'lua_dao' for c in cases)} scam, "
             f"{sum(c['nhom'] == 'binh_thuong' for c in cases)} ordinary), {len(dropped)} dropped.\n")
    L += ["### Every dropped case\n", "| Case | Round | Opening | Re-read: scam type | Reason |", "|---|---|---|---|---|"]
    for d in dropped:
        L.append(f"| `{d['id']}` | {d.get('vong', 0)} | {d['tin_mo_dau']} | `{d['doc_lai']['kich_ban']}` | "
                 f"{d['doc_lai']['ly_do']} |")
    pick = sorted(random.Random(f"{SEED}:T6:viec").sample(sorted(viec), 5))
    L += ["\n### All purpose lines of five scenarios (seeded draw)\n",
          f"Drawn with `random.Random('{SEED}:T6:viec')`. Lines in order; the first N went to the cases, the rest were "
          "spare for replacements.\n"]
    for s in pick:
        L.append(f"**{tag(s)}** ({nhom[s]}, {len(viec[s]['lines'])} lines)\n")
        L += [f"{i + 1}. {t}" for i, t in enumerate(viec[s]["lines"])]
        L.append("")
    rng = random.Random(f"{SEED}:T6:show")
    show = sorted(rng.sample([c for c in cases if c["nhom"] == "binh_thuong"], 5), key=lambda c: c["id"]) + \
        sorted(rng.sample([c for c in cases if c["nhom"] == "lua_dao"], 5), key=lambda c: c["id"])
    sess_by = {r["case"]: r for r in sess}
    L += ["### Ten cases in full (seeded draw: five ordinary, five scam)\n",
          f"Drawn with `random.Random('{SEED}:T6:show')`. Story table, account facts, purpose line, opening, re-read "
          "verdict; and the part C dialogue when it ran.\n"]
    for c in show:
        L += [f"#### `{c['id']}` ({c['nhom']}, persona `{c['tinh_cach']}`)\n",
              f"- Purpose line: *{c['viec']}*",
              "- Table: " + "; ".join(f"`{k}` {', '.join(v) if isinstance(v, list) else v}"
                                      for k, v in c["bang_that"].items()),
              "- Account: " + "; ".join(f"`{k}` {v}" for k, v in c["tai_khoan"].items()),
              f"- Opening: {c['tin_mo_dau']}"]
        if "doc_lai" in c:
            L.append(f"- Re-read: not flagged. {c['doc_lai'].get('ly_do', '')}")
        r = sess_by.get(c["id"])
        if r:
            L.append(f"- Part C dialogue (flash-lite answers after 0..3 questions: "
                     f"{', '.join(f'`{p}`' for p in r['preds'])}):")
            for h in r["history"]:
                L.append(f"  - {'User' if h['role'] == 'user' else 'Assistant'}: {h['text']}")
        L.append("")

    # ---------------------------------------------------------------- part C
    L.append("## Part C - flash-lite baseline on test set v2\n")
    if not sess:
        L.append("Not run yet.\n")
    else:
        v1rows = [r for r in load_rows(ROOT / "experiments/E5/sessions.jsonl") if "preds" in r and r["model"] == BASE]
        S, S1 = score(sess, scen), score(v1rows, scen)
        L += [f"`{BASE}`, `tu_do` prompt with the 25-scenario catalogue, at most {K} questions, simulated user "
              f"`{BASE}` with `VICTIM_PROMPT_VIEC` (part B2). One run, jobs in seeded round-robin order over the "
              f"scenarios (`--order-seed {SEED}`). Scam: {sum(r['nhom'] == 'lua_dao' for r in sess)} sessions, ordinary "
              f"{sum(r['nhom'] == 'binh_thuong' for r in sess)}. USD per session includes the simulated user.\n",
              *HEAD,
              f"| v2 (this run) | {S['n']} | {metric_rows(S)} |",
              f"| v1 (E5, `sim/cases/`) | {S1['n']} | {metric_rows(S1)} |",
              "\n**The two sets are not comparable**: v1 has 15 scenarios and the E5 run used the 15-scenario catalogue "
              "and the old simulated-user prompt; v2 has 25 scenarios, new purpose lines and openings by another model "
              "family, and the B2 simulated user. The v1 row is context, not a before/after.\n",
              "### Split by account label (`nhan_tai_khoan`, shown to the assistant)\n", *HEAD]
        labs = defaultdict(set)
        for r in sess:
            labs[account(by_id[r["case"]])].add(r["case"])
        for lab in sorted(labs):
            s = score(sess, scen, labs[lab])
            L.append(f"| `{lab}` | {s['n']} | {metric_rows(s)} |")
        L += ["\nBy group and label:\n", "| Group | Label | Sessions | Correct after 3 q | Scam called ordinary / ordinary "
              f"flagged | `{CHUA_DU}` |", "|---|---|---|---|---|---|"]
        for g, key in (("lua_dao", "miss"), ("binh_thuong", "fp")):
            for lab in sorted(labs):
                ids = {i for i in labs[lab] if by_id[i]["nhom"] == g}
                if ids:
                    s = score(sess, scen, ids)
                    L.append(f"| {g} | `{lab}` | {s['n']} | {fmt(s['kb3'])} | {fmt(s[key])} | {fmt(s['chua_du'])} |")
        L += ["\n## Second opinion: C0 v2 and C0 v3 behind flash-lite\n",
              "Scored as in the E6 report: the classifier reads the user's words of the same session; see the docstring "
              "of `e6/t6_report.py`. C0 v3's val shares its purpose lines with its train set (T4b), so its tau is set "
              "on an optimistic val.\n"]
        for name, (ver, mdir) in CLS.items():
            second_opinion(L, name, SCEN_V2, mdir, ROOT / f"data/E6/{ver}/preds/c0.jsonl", sess, scen)
        L += ["## The classifiers alone on the 475 openings\n",
              "| Classifier | Correct scenario | Scam called ordinary | Ordinary called scam | Correct on the new scenarios |",
              "|---|---|---|---|---|"]
        for name, (ver, mdir) in CLS.items():
            L.append(alone(name, SCEN_V2, mdir, cases, scen))
        ps, p1 = per_scenario(sess, scen), per_scenario(v1rows, scen)
        L += ["\n## Per scenario (flash-lite, correct after 3 questions)\n",
              "| Scenario | Group | v2 | v1 (E5, not comparable) |", "|---|---|---|---|"]
        for s in SCEN_V2:
            cell = lambda p: f"{100 * p[s]['p']:.0f}% ({p[s]['k']}/{p[s]['n']})" if s in p else "-"  # noqa: E731
            L.append(f"| {tag(s)} | {nhom[s]} | {cell(ps)} | {cell(p1)} |")
        L += ["\nMost frequent confusions on v2 (true -> answered after 3 questions): "
              + "; ".join(f"`{a}` -> `{b}` {n}" for (a, b), n in confusions(sess, 10)) + "\n"]
        if old_sess:
            new45 = [r for r in sess if r["case"] in a2_ids]
            L += [f"## The {len(a2_ids)} cases rewritten by part A2\n",
                  "Same tables and ids; the old sessions ran on the drifted purpose lines and openings, the new ones on "
                  "the rewritten ones. The main tables above use the new ones.\n", *HEAD]
            for name, rs in (("before A2", old_sess), ("after A2", new45)):
                if rs:
                    L.append(f"| {name} | {len(rs)} | {metric_rows(score(rs, scen))} |")
            po, pn = per_scenario(old_sess, scen), per_scenario(new45, scen)
            L += ["", "| Scenario | Before A2 | After A2 |", "|---|---|---|"]
            for s in sorted(A2_CORES):
                cell = lambda p: f"{100 * p[s]['p']:.0f}% ({p[s]['k']}/{p[s]['n']})" if s in p else "-"  # noqa: E731
                L.append(f"| {tag(s)} | {cell(po)} | {cell(pn)} |")
            L.append("")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("report:", (OUT / "report.md").relative_to(ROOT))


if __name__ == "__main__":
    main()
