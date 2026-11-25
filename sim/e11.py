"""E11: chat with gemini-3.8-flash at high thinking on the 75 `v1` cases, next to the other models' `v1` sessions.

    python -m sim.e5 --models gemini-3.8-flash@high --cap-usd 1.8 --project-after 30   # the run (E5 protocol)
    python -m sim.e11                                                                     # this report

Reads experiments/E5/sessions.jsonl, writes experiments/E11/report.md. No API calls.
"""
from __future__ import annotations

import statistics

from core.scenarios import ROOT, load
from e1.score import wilson
from sim.e5 import OUT as E5_OUT, fmt, load_rows, pctl, score
from sim.e10_d import paired
from sim.run import CHUA_DU, K

OUT = ROOT / "experiments/E11"
NEW = "gemini-3.8-flash@high"
LOW = "gemini-3.8-flash@low"
BASE = "gemini-3.5-flash-lite"
MODELS = [NEW, LOW, BASE, "gemini-3.5-flash-lite@medium", "gemini-4-carbon", "openai:gpt-6.2-sol",
          "anthropic:claude-haiku-5-5", "local:gemma-4-e4b-qat"]


def called_ordinary(r, scen) -> bool:
    p = r["preds"][K]
    return p != CHUA_DU and scen[p].nhom == "binh_thuong"


def thinking(model, turns) -> str:
    """Thinking tokens per call: only Gemini reports them apart from the answer, and only rows run after E5 recorded
    the field; Anthropic folds them into the output tokens; the open models run with thinking off."""
    if model.startswith("local:"):
        return "off"
    if model.startswith("gemini") and all("tokens_thought" in t for t in turns):
        th = [t["tokens_thought"] or 0 for t in turns]
        return f"{statistics.median(th):.0f}, {pctl(th, 0.9):.0f}"
    return "not recorded" if model.startswith("gemini") else "not reported apart"


def mean_p90(xs) -> str:
    return f"{sum(xs) / len(xs):.2f}, {pctl(xs, 0.9):.2f}" if xs else "-"


def main():
    scen, issues = load()
    assert not issues, issues
    v1 = [r for r in load_rows(E5_OUT / "sessions.jsonl") if "preds" in r and r.get("v1")]
    new_rows = [r for r in load_rows(E5_OUT / "sessions.jsonl") if r.get("model") == NEW]
    all_v1 = {m: [r for r in v1 if r["model"] == m] for m in MODELS}
    cases = {r["case"] for r in all_v1[NEW]}
    by = {m: [r for r in rs if r["case"] in cases] for m, rs in all_v1.items()}
    errors = sum("error" in r for r in new_rows)
    usd = [r["usd"] + r.get("victim_usd", 0) for r in by[NEW]]
    spent, victim = sum(usd), sum(r.get("victim_usd", 0) for r in by[NEW])
    S = {m: score(rs, scen) for m, rs in by.items() if rs}
    n, n_scam, n_ord = S[NEW]["n"], S[NEW]["miss"]["n"], S[NEW]["fp"]["n"]
    n_all = len(all_v1[BASE])
    lo, hi = wilson(round(0.75 * n), n)
    scam_scen = sorted({r["kich_ban"] for r in by[NEW] if r["nhom"] == "lua_dao"})
    all_scam_scen = {r["kich_ban"] for r in all_v1[BASE] if r["nhom"] == "lua_dao"}
    co = lambda r: called_ordinary(r, scen)  # noqa: E731
    worst = max(by[NEW], key=lambda r: r["usd"])
    think_max = max(t.get("tokens_thought") or 0 for r in by[NEW] for t in r["turns"])

    L = [f"# E11 - Chat with `{NEW}` (high thinking), {n} `v1` cases\n",
         f"Brief: `docs/tasks/E11-chat-gemini-3.8-flash-high.md`. Go: Minh, 2026-11-25. Run: `python -m sim.e5 --models "
         f"{NEW} --cap-usd 1.8 --project-after 30` (E5 protocol: `tu_do` prompt unchanged, simulated user "
         f"`{BASE}`, one run, 8 sessions in parallel). Report: `python -m sim.e11`.\n",
         f"**Spend (recorded): {spent:.3f} USD** for {n} sessions (assistant {spent - victim:.3f}, simulated user "
         f"{victim:.3f}); cap 1.8 USD. Sessions that ended in an error: {errors}. The run log's in-process total "
         "(every billed call) is the same.\n"]
    if n < n_all:
        L.append(f"**Stopped by the projection rule after {n} sessions.** Projection: {spent / n:.4f} USD per session "
                 f"x {n_all} = {spent / n * n_all:.3f} USD, over the 1.8 USD cap, so by the brief the run stopped at "
                 f"those {n} sessions (the runner started no session past them). The planner's estimate was 0.010-0.026 "
                 f"USD per session; the mean is {spent / n:.4f}, with a heavy tail: median {sorted(usd)[n // 2]:.4f}, "
                 f"the most expensive session {worst['usd'] + worst.get('victim_usd', 0):.4f} USD and "
                 f"{worst['seconds']:.0f} s (`{worst['case']}`), the longest single call {think_max} thinking tokens.\n")
        L.append(f"**What the {n} sessions cover.** The runner queues cases in case-id order (as in E5), so the first "
                 f"{n} are the first {len({r['kich_ban'] for r in by[NEW]})} scenarios alphabetically: all {n_ord} "
                 f"ordinary cases, but only {n_scam} of the {sum(r['nhom'] == 'lua_dao' for r in all_v1[BASE])} scam "
                 f"cases, from {len(scam_scen)} of the {len(all_scam_scen)} scam scenarios ("
                 + ", ".join(f"`{s}`" for s in scam_scen) + "). The brief's main question, scams called ordinary, is "
                 "therefore measured on those few scam cases only; the last section shows where the other models' "
                 "misses are.\n")
    L += [f"**No rule was declared in advance.** On {n} cases a 95% interval around 75% runs from {100 * lo:.0f}% to "
          f"{100 * hi:.0f}%, so this run describes cost and direction; it decides nothing by itself.\n",
          f"Every row below is on the same {n} cases ({n_scam} scam, {n_ord} ordinary). Rates as k/n [Wilson 95%]. "
          "Other models: the E5 / E10 sessions already run (no new calls).\n",
          "## Outcomes\n",
          "| Model | Correct after 0 questions | after 1 | after 2 | after 3 | Scam called ordinary | Ordinary flagged as "
          "scam | `chua_du_can_cu` | Questions |",
          "|---|---|---|---|---|---|---|---|---|"]
    for m, s in S.items():
        L.append(f"| `{m}` | " + " | ".join(fmt(s[f"kb{k}"]) for k in range(K + 1))
                 + f" | {fmt(s['miss'])} | {fmt(s['fp'])} | {fmt(s['chua_du'])} | {s['q']:.2f} |")

    L += ["\n## Cost and time\n",
          "A call either asks a question or concludes (the last call of a session). Model seconds per session exclude "
          "the simulated user. Seconds are wall time per API call with 8 sessions in parallel; `gemma-4-e4b-qat` ran "
          "on the server GPU (8 sessions sharing it). USD per session: the assistant only.\n",
          "| Model | Thinking tokens per call (median, p90) | Output tokens per call, thinking included (median, p90) "
          "| s per asking call (mean, p90) | s per concluding call (mean, p90) | Model s per session (mean, p90) | "
          "USD per session |",
          "|---|---|---|---|---|---|---|"]
    for m, rs in by.items():
        if not rs:
            continue
        turns = [t for r in rs for t in r["turns"]]
        ask = [t["seconds"] for r in rs for t in r["turns"][:-1]]
        end = [r["turns"][-1]["seconds"] for r in rs]
        out = [t["tokens_out"] for t in turns]
        L.append(f"| `{m}` | {thinking(m, turns)} | {statistics.median(out):.0f}, {pctl(out, 0.9):.0f} | "
                 f"{mean_p90(ask)} | {mean_p90(end)} | {mean_p90([r['seconds'] for r in rs])} | "
                 f"{S[m]['usd']:.5f} |")

    L += ["\n## Paired comparisons (same cases)\n",
          "Difference A - B with a paired bootstrap 95% interval; exact McNemar on the discordant cases.\n",
          "| A vs B | Outcome | n | Both | Only A | Only B | Neither | A - B | McNemar p |",
          "|---|---|---|---|---|---|---|---|---|"]
    for b in (LOW, BASE):
        for label, ok, sub in (("correct scenario after 3", None, lambda r: True),
                               ("scam called ordinary (scam cases)", co, lambda r: r["nhom"] == "lua_dao")):
            ra, rb = [r for r in by[NEW] if sub(r)], [r for r in by[b] if sub(r)]
            p = paired(ra, rb, ok) if ok else paired(ra, rb)
            L.append(f"| `{NEW}` vs `{b}` | {label} | {p['n']} | {p['both']} | {p['a_only']} | {p['b_only']} | "
                     f"{p['neither']} | {100 * p['diff']:+.1f} [{100 * p['lo']:+.1f}, {100 * p['hi']:+.1f}] | "
                     f"{p['p']:.3f} |")

    three = (NEW, LOW, BASE)
    pred = {m: {r["case"]: r for r in by[m]} for m in three}
    missed = sorted({c for m in three for c, r in pred[m].items() if r["nhom"] == "lua_dao" and co(r)})
    L += ["\n## Scam cases called ordinary\n",
          "Final conclusion of each model on every scam case that at least one of the three calls ordinary "
          "(**bold** = called ordinary).\n"]
    if missed:
        L += ["| Case | Scenario | " + " | ".join(f"`{m}`" for m in three) + " |", "|---|---|" + "---|" * len(three)]
    for c in missed:
        cells = [f"**{pred[m][c]['preds'][K]}**" if co(pred[m][c]) else pred[m][c]["preds"][K] for m in three]
        L.append(f"| `{c}` | `{pred[NEW][c]['kich_ban']}` | " + " | ".join(cells) + " |")
    L.append(f"{'' if missed else 'None on these cases. '}Count on the {n} cases: "
             + ", ".join(f"`{m}` {sum(co(r) for r in by[m] if r['nhom'] == 'lua_dao')}/{n_scam}" for m in three)
             + ".\n")
    if n < n_all:
        L += [f"On the {n_all - n} `v1` cases this run did not reach (E5 sessions of the other two):\n",
              "| Model | Scam called ordinary | Cases (case -> conclusion) |", "|---|---|---|"]
        for m in (LOW, BASE):
            rest = [r for r in all_v1[m] if r["case"] not in cases and r["nhom"] == "lua_dao"]
            bad = sorted((r for r in rest if co(r)), key=lambda r: r["case"])
            L.append(f"| `{m}` | {len(bad)}/{len(rest)} | "
                     + "; ".join(f"`{r['case']}` -> `{r['preds'][K]}`" for r in bad) + " |")
        L.append("")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    s = S[NEW]
    print(f"{NEW} n={n} kb3={fmt(s['kb3'])} miss={fmt(s['miss'])} fp={fmt(s['fp'])} q={s['q']:.2f} "
          f"spent={spent:.3f}")
    print("report:", (OUT / "report.md").relative_to(ROOT))


if __name__ == "__main__":
    main()
