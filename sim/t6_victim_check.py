"""T6 part B2 check: does the simulated user still invent details? 40 ordinary and 20 scam `val` rows of
data/E6/cases_v2.jsonl (seeded, round-robin over scenarios), one fixed question after the opening, answered with the
old prompt (VICTIM_PROMPT) and the new one (VICTIM_PROMPT_VIEC). All 120 answers go to experiments/T6/victim_check.md
with the account facts and `mo_ta`; contradictions are counted by eye.

  python -m sim.t6_victim_check
"""
from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor

from core import llm
from core.scenarios import ROOT, load
from sim.run import account_facts, victim_reply

OUT = ROOT / "experiments/T6"
QUESTION = "Bạn lấy số tài khoản này từ đâu, và tên chủ tài khoản hiện lên là tên ai?"
N = {"binh_thuong": 40, "lua_dao": 20}


def pick(rows, scen, nhom, n, rng):
    by = {}
    for r in rows:
        if r["split"] == "val" and r["nhom"] == nhom:
            by.setdefault(r["kich_ban"], []).append(r)
    order = sorted(by)
    rng.shuffle(order)
    for sid in order:
        rng.shuffle(by[sid])
    out, i = [], 0
    while len(out) < n:
        out += [by[sid][i] for sid in order if i < len(by[sid])][:n - len(out)]
        i += 1
    return out


def main():
    scen, issues = load()
    assert not issues, issues
    rows = [json.loads(line) for line in open(ROOT / "data/E6/cases_v2.jsonl", encoding="utf-8")]
    rng = random.Random("T6:B2")
    sample = [r for nhom, n in N.items() for r in pick(rows, scen, nhom, n, rng)]
    history = lambda r: [{"role": "user", "text": r["tin_mo_dau"]}, {"role": "assistant", "text": QUESTION}]  # noqa: E731
    jobs = [(r, old) for r in sample for old in (True, False)]
    with ThreadPoolExecutor(6) as ex:
        answers = list(ex.map(lambda j: victim_reply(j[0], scen, history(j[0]), old=j[1]).text, jobs))
    got = {(r["id"], old): a for (r, old), a in zip(jobs, answers)}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "victim_check.jsonl", "w", encoding="utf-8") as f:
        for r in sample:
            f.write(json.dumps({"id": r["id"], "kich_ban": r["kich_ban"], "nhom": r["nhom"],
                                "old": got[(r["id"], True)], "new": got[(r["id"], False)]}, ensure_ascii=False) + "\n")
    L = ["# T6 part B2 - simulated user, old prompt vs new prompt\n",
         f"{len(sample)} `val` rows of `data/E6/cases_v2.jsonl` ({N['binh_thuong']} ordinary, {N['lua_dao']} scam; "
         "seeded `random.Random('T6:B2')`, round-robin over scenarios). One fixed question after the opening: "
         f"*{QUESTION}* Old: `sim.run.VICTIM_PROMPT` (the story text of T4b). New: `sim.run.VICTIM_PROMPT_VIEC` (adds "
         "the two account facts; off-table questions answered from `mo_ta`, else \"not sure / not checked\"; no new "
         f"detail). Simulated user `gemini-3.5-flash-lite`, {llm.USAGE.calls} calls, {llm.USAGE.usd:.4f} USD. "
         "Report: `python -m sim.t6_victim_check`.\n"]
    for i, r in enumerate(sample, 1):
        s, t = scen[r["kich_ban"]], r["bang_that"]
        L += [f"## {i}. `{r['id']}` ({r['nhom']})\n",
              f"- Account: `loai_tai_khoan {t['loai_tai_khoan']}`, `ten_khop_tu_xung {t['ten_khop_tu_xung']}` "
              f"(`tu_xung {t['tu_xung']}`). New prompt shows: " + " / ".join(account_facts(t).splitlines()),
              f"- Purpose line: *{r['viec']}*",
              f"- `mo_ta`: {' '.join(s.mo_ta.split())}",
              f"- Opening: {r['tin_mo_dau']}",
              f"- **Old:** {got[(r['id'], True)]}",
              f"- **New:** {got[(r['id'], False)]}\n"]
    (OUT / "victim_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(sample)} rows, {llm.USAGE.calls} calls, {llm.USAGE.usd:.4f} USD ->",
          (OUT / "victim_check.md").relative_to(ROOT))


if __name__ == "__main__":
    main()
