"""E12 report: untrained Qwen3-4B-Instruct-2507 as the chat model on test set v2 -> experiments/E12/report.md.

  python3 -m e6.e12_report

Inputs: experiments/E12/sessions.jsonl and meta.json (server run, `bash scripts/e12_run.sh`, pulled back),
experiments/T6/sessions.jsonl (the flash-lite rows of T6 part C, same cases, same order seed), sim/cases_v2/.
Rows pair case by case. Paired comparisons: 2x2 table, exact McNemar, difference with a paired bootstrap 95%.
The account rule is the planner's (chosen on this test set): an ordinary conclusion becomes "caution" when the account
label is not `moi`, or when the name does not match and the conclusion is not `bt_tra_shipper_khi_nhan_hang`.
The section helpers are shared with e6/e13_report.py.
"""
from __future__ import annotations

import json
from collections import defaultdict

from core.scenarios import ROOT, load
from e6.t6_report import NEW, account, subsets, tag
from sim.e10_d import mcnemar_p
from sim.e5 import K, confusions, fmt, load_cases, load_rows, pctl, rate, score
from sim.run import CHUA_DU, bootstrap

OUT = ROOT / "experiments/E12"
QWEN = "local:qwen3-4b-instruct-2507"
FLASH = "gemini-3.5-flash-lite"
CAP = 0.35
SHIPPER = "bt_tra_shipper_khi_nhan_hang"

HEAD = ("| Model | Set | Sessions | Scam called ordinary | Ordinary flagged as scam | Correct after 0 q | after 1 | "
        f"after 2 | after 3 | `{CHUA_DU}` | Questions | Malformed turns (retried) | Answer outside the catalogue | "
        "s/turn mean | s/turn p90 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def main_row(name, sub, S, n):
    """Rows without turn records (the teacher's sessions) show "-" in the turn columns."""
    tc = (f"{S['retries']} of {S['turns']} | {fmt(S['bad_format'])} | {S['sec_mean']:.2f} | {S['sec_p90']:.2f}"
          if S["turns"] else "- | - | - | -")
    return (f"| {name} | {sub} | {n} | {fmt(S['miss'])} | {fmt(S['fp'])} | {fmt(S['kb0'])} | {fmt(S['kb1'])} | "
            f"{fmt(S['kb2'])} | {fmt(S['kb3'])} | {fmt(S['chua_du'])} | {S['q']:.2f} | {tc} |")


def is_ordinary(ans, nhom):
    return ans not in (CHUA_DU, "caution") and nhom[ans] == "binh_thuong"


def is_scam(ans, nhom):
    return ans not in (CHUA_DU, "caution") and nhom[ans] == "lua_dao"


def load_all():
    """-> scen, nhom (scenario -> group), cases of sim/cases_v2, by_id."""
    scen, issues = load()
    assert not issues, issues
    cases = load_cases(ROOT / "sim/cases_v2")
    return scen, {s: scen[s].nhom for s in scen}, cases, {c["id"]: c for c in cases}


def flash_rows(ids=None):
    rs = [r for r in load_rows(ROOT / "experiments/T6/sessions.jsonl") if "preds" in r and r["model"] == FLASH]
    return [r for r in rs if ids is None or r["case"] in ids]


def main_tables(L, runs, names, scen, by_id):
    """runs: {model: rows} in display order (same cases)."""
    ids = set.intersection(*({r["case"] for r in rs} for rs in runs.values()))
    not_a2 = {i for i in ids if not by_id[i].get("a2")}
    L += ["## Main rows\n",
          "Columns in Minh's order: scam called ordinary, ordinary flagged as scam, correct scenario, then the rest. "
          "\"Malformed turns\" = replies that did not parse and were asked again; \"answer outside the catalogue\" = "
          "turns whose answer was not a scenario id.\n", *HEAD]
    for m, rs in runs.items():
        L.append(main_row(names[m], f"all {len(ids)}", score(rs, scen, ids), len(ids)))
    for m, rs in runs.items():
        L.append(main_row(names[m], f"{len(not_a2)} not rewritten by A2", score(rs, scen, not_a2), len(not_a2)))
    L.append("\nThe 45 cases rewritten by T6 part A2 state the scam's mechanism in the opening, so they are easy by "
             "construction; the second block of rows leaves them out.\n")
    L += ["### Split by group and by account label (`nhan_tai_khoan`, shown to the assistant)\n", *HEAD]
    for sub, s_ids in subsets(ids, by_id)[1:]:
        for m, rs in runs.items():
            L.append(main_row(names[m], sub, score(rs, scen, s_ids), len(s_ids)))
    L.append("")


def paired(L, title, a, b, an, bn):
    """a, b: {case: ok} of models named an, bn; 2x2, difference a - b [paired bootstrap 95%], exact McNemar."""
    keys = sorted(set(a) & set(b))
    if not keys:
        return
    tt = sum(a[k] and b[k] for k in keys)
    tf = sum(a[k] and not b[k] for k in keys)
    ft = sum(b[k] and not a[k] for k in keys)
    ff = len(keys) - tt - tf - ft
    d = [float(a[k]) - float(b[k]) for k in keys]
    lo, hi = bootstrap(d)
    L += [f"**{title}, {an} vs {bn}** (n = {len(keys)})\n", f"| | {bn} yes | {bn} no |", "|---|---|---|",
          f"| {an} yes | {tt} | {tf} |", f"| {an} no | {ft} | {ff} |",
          f"\n{an} - {bn}: {100 * sum(d) / len(d):+.1f} points [{100 * lo:+.1f}, {100 * hi:+.1f}], "
          f"McNemar p = {mcnemar_p(tf, ft):.3g}.\n"]


def paired_pair(L, ra, rb, an, bn, by_id, nhom):
    """Correct scenario and scam not called ordinary, model rows ra vs rb."""
    aa = {r["case"]: r["preds"][K] for r in ra}
    ab = {r["case"]: r["preds"][K] for r in rb}
    paired(L, "Correct scenario after 3 questions", {k: v == by_id[k]["kich_ban"] for k, v in aa.items()},
           {k: v == by_id[k]["kich_ban"] for k, v in ab.items()}, an, bn)
    paired(L, "Scam NOT called ordinary (scam cases only)",
           {k: not is_ordinary(v, nhom) for k, v in aa.items() if by_id[k]["nhom"] == "lua_dao"},
           {k: not is_ordinary(v, nhom) for k, v in ab.items() if by_id[k]["nhom"] == "lua_dao"}, an, bn)


def account_rule(ans, c, nhom):
    if ans == CHUA_DU or nhom[ans] != "binh_thuong":
        return ans
    tk = c.get("tai_khoan", {})
    if tk.get("nhan_tai_khoan") != "moi" or (tk.get("ten_khop_tu_xung") == "khong" and ans != SHIPPER):
        return "caution"
    return ans


def account_rule_table(L, runs, names, by_id, nhom):
    L += ["## Reference: the account rule applied after the model\n",
          "**Rule chosen by the planner on this test set** (not declared in advance, so it is a reference only): an "
          "ordinary conclusion becomes \"caution\" when the account label is not `moi`, or when the name does not "
          f"match and the conclusion is not `{SHIPPER}`.\n",
          "| Model | Scam still called ordinary | Ordinary moved to caution | Ordinary flagged as scam | Scam moved to "
          "caution |", "|---|---|---|---|---|"]
    for m, rs in runs.items():
        after = {r["case"]: account_rule(r["preds"][K], by_id[r["case"]], nhom) for r in rs}
        scam = [k for k in after if by_id[k]["nhom"] == "lua_dao"]
        ordi = [k for k in after if by_id[k]["nhom"] == "binh_thuong"]
        L.append(f"| {names[m]} | {fmt(rate(sum(is_ordinary(after[k], nhom) for k in scam), len(scam)))} | "
                 f"{fmt(rate(sum(after[k] == 'caution' for k in ordi), len(ordi)))} | "
                 f"{fmt(rate(sum(is_scam(after[k], nhom) for k in ordi), len(ordi)))} | "
                 f"{fmt(rate(sum(after[k] == 'caution' for k in scam), len(scam)))} |")
    L.append("")


def per_scenario_table(L, runs, names, nhom):
    ps = {m: defaultdict(list) for m in runs}
    for m, rs in runs.items():
        for r in rs:
            ps[m][r["kich_ban"]].append(r["preds"][K] == r["kich_ban"])
    L += ["## Per scenario (correct after 3 questions)\n", "| Scenario | Group | " + " | ".join(names[m] for m in runs)
          + " |", "|---|---|" + "---|" * len(runs)]
    for sid in sorted(set().union(*ps.values())):
        cells = [f"{100 * sum(v) / len(v):.0f}% ({sum(v)}/{len(v)})" if (v := ps[m][sid]) else "-" for m in runs]
        L.append(f"| {tag(sid)} | {nhom[sid]} | " + " | ".join(cells) + " |")
    for m, rs in runs.items():
        L.append(f"\nMost frequent confusions of {names[m]} (true -> answered after 3 questions): "
                 + "; ".join(f"`{a}` -> `{b}` {n}" for (a, b), n in confusions(rs, 10)))
    L.append("")


def missed_table(L, rs, name, others, by_id, nhom):
    """Every scam case of rs called ordinary; others: {short name: rows} marked when they missed the case too."""
    oth = {n: {r["case"]: r["preds"][K] for r in o} for n, o in others.items()}
    missed = sorted((r for r in rs if r["nhom"] == "lua_dao" and is_ordinary(r["preds"][K], nhom)),
                    key=lambda r: r["case"])
    L += [f"## Every scam case {name} called ordinary ({len(missed)})\n",
          "| Case | Scenario | Account label | Answer | Questions | " + " | ".join(f"{n} also" for n in oth)
          + " | Opening |", "|---|---|---|---|---|" + "---|" * len(oth) + "---|"]
    for r in missed:
        also = ["yes" if is_ordinary(o.get(r["case"], CHUA_DU), nhom) else "no" for o in oth.values()]
        op = by_id[r["case"]]["tin_mo_dau"].replace("|", "/").replace("\n", " ")
        L.append(f"| `{r['case']}` | {tag(r['kich_ban'])} | `{account(by_id[r['case']])}` | `{r['preds'][K]}` | "
                 f"{r['n_asked']} | " + " | ".join(also) + f" | {op} |")
    L.append("")


def run_facts(rs):
    turns = [t for r in rs for t in r["turns"]]
    secs = [t["seconds"] for t in turns]
    return {"turns": len(turns), "longest_prompt": max((t["tokens_in"] for t in turns), default=0),
            "think": sum("<think" in json.dumps(r, ensure_ascii=False) for r in rs),
            "victim_usd": sum(r.get("victim_usd", 0) for r in rs),
            "secs": (sum(secs) / max(1, len(secs)), pctl(secs, 0.5), pctl(secs, 0.9), max(secs, default=0))}


def main():
    scen, nhom, cases, by_id = load_all()
    raw = load_rows(OUT / "sessions.jsonl")
    errors = [r for r in raw if "error" in r and r["model"] == QWEN]
    qw = [r for r in raw if "preds" in r and r["model"] == QWEN]
    fl = flash_rows({r["case"] for r in qw})
    meta = json.loads((OUT / "meta.json").read_text()) if (OUT / "meta.json").exists() else {}
    f = run_facts(qw)
    runs = {QWEN: qw, FLASH: fl}
    names = {QWEN: "`qwen3-4b-instruct-2507` (untrained)", FLASH: "`gemini-3.5-flash-lite` (T6 part C)"}

    L = ["# E12 - Untrained Qwen3-4B-Instruct-2507 as the chat model, on test set v2\n",
         "Brief: `docs/tasks/E12-chat-qwen3-4b-untrained.md`. Report: `python3 -m e6.e12_report`. Rates as k/n "
         "[Wilson 95%]; one run.\n",
         "## Spend\n",
         f"Gemini (`{FLASH}`, simulated user only): **{f['victim_usd']:.4f} USD** for {len(qw)} sessions (cap {CAP}). "
         "The chat model runs on the company server's RTX 4060 Ti 16 GB: no API cost.\n",
         "## Run\n",
         f"`{meta.get('repo', 'Qwen/Qwen3-4B-Instruct-2507')}`, revision `{meta.get('revision', '?')}`, licence "
         f"{meta.get('licence') or 'apache-2.0 (Hugging Face model card, read 2026-11-26)'}, "
         f"{meta.get('quant', 'bf16')}, served by vLLM ({meta.get('versions', '?')}): "
         f"context {meta.get('max_model_len', '?')} tokens, `gpu_memory_utilization` "
         f"{meta.get('gpu_memory_utilization', '?')}, at most 8 sequences, greedy (a retry after a malformed reply "
         "samples at 0.7), thinking off, JSON schema enforced. Same protocol as T6 part C: `python -m sim.e5 --cases "
         "sim/cases_v2 --order-seed 20261128`, `tu_do` prompt with the 25-scenario catalogue, at most 3 questions, "
         "simulated user `gemini-3.5-flash-lite` with `VICTIM_PROMPT_VIEC`.\n",
         "| Weights on disk | Weights in vLLM | KV cache | Peak VRAM (whole card) | Server start | Longest prompt | "
         "`<think>` in a session | Sessions with an error |", "|---|---|---|---|---|---|---|---|",
         f"| {meta.get('weights_gb_disk', '?')} GB | {meta.get('weights_gib_vllm', '?')} GiB | "
         f"{meta.get('kv_cache_gib', '?')} GiB | {meta.get('vram_peak_mib', '?')} MiB | "
         f"{meta.get('server_start_s', '?')} s | {f['longest_prompt']:,} tokens | {f['think']} of {len(qw)} | "
         f"{len(errors)} |\n"]
    if len(qw) < len(cases):
        L.append(f"**Partial run: {len(qw)} of {len(cases)} cases.** flash-lite rows below are on the same cases.\n")
    main_tables(L, runs, names, scen, by_id)
    L.append("## Paired against flash-lite on the same cases\n")
    paired_pair(L, qw, fl, "Qwen", "flash-lite", by_id, nhom)
    account_rule_table(L, runs, names, by_id, nhom)
    per_scenario_table(L, runs, names, nhom)
    missed_table(L, qw, "Qwen", {"flash-lite": fl}, by_id, nhom)
    s = f["secs"]
    L.append(f"Turns: {f['turns']}; seconds per turn mean {s[0]:.2f}, p50 {s[1]:.2f}, p90 {s[2]:.2f}, max {s[3]:.2f} "
             f"(8 sessions in parallel on one card). New scenarios: {', '.join(f'`{x}`' for x in NEW)}.\n")
    (OUT / "report.md").write_text("\n".join(L), encoding="utf-8")
    print("report:", (OUT / "report.md").relative_to(ROOT))


if __name__ == "__main__":
    main()
