"""E13 report: LoRA runs on Qwen3-4B-Instruct-2507 as the chat model on test set v2 -> experiments/E13/report.md.

  python3 -m e6.e13_report

Inputs: experiments/E13/sessions.jsonl and meta.json (server, `RUN=<name> bash scripts/e13_run.sh`, pulled back;
meta.json holds each run's training meta from e1.chat_lora plus its serving facts, keyed by run name; the run's
sessions are model `local:qwen3-4b-e13-<run>`), experiments/E12/sessions.jsonl (untrained), experiments/T6/
sessions.jsonl (flash-lite), sim/cases_v2/. Section helpers from e6/e12_report.py.

Rule declared in the brief before any result: a fine-tuned model is "as good as the closed model" if on the 475 cases
it is no more than 5 points behind flash-lite on correct scenario, calls no more scams ordinary than flash-lite (18/225)
and flags no more than 14/250 ordinary transfers (flash-lite 2/250 plus 5 points).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from core.scenarios import ROOT
from e6 import e12_report as e12
from e6.e12_report import (CAP, FLASH, QWEN, account_rule_table, flash_rows, is_ordinary, load_all, main_tables,
                           missed_table, paired_pair, per_scenario_table, run_facts)
from e6.t6_report import account, tag
from sim.e5 import K, fmt, load_rows, rate, score
from sim.run import CHUA_DU

OUT = ROOT / "experiments/E13"
PREFIX = "local:qwen3-4b-e13-"
OPUS = "teacher:claude-opus-5-5"
OPUS_SESSIONS = ROOT / "data/T5/test_v2_opus_sessions.jsonl"  # T5 part 6, experiments/T5/test_v2_opus.md
DATA_NOTES = {  # what each training file holds, as the planner described it when sending the run
    "data/T5/opus/train_final.jsonl": "the Opus 5.5 sessions kept by T5, plus the ordinary sessions the teacher ended "
    "with `chua_du_can_cu` (Minh counts that as a safe outcome), plus recovered hard cases; its val file "
    "`data/T5/opus/val_all.jsonl` is built the same way without the recovered cases. The planner checked: no duplicate "
    "(story, turn), no story in both train and val, no test-set opening.",
}


def teacher(train_path):
    return "Opus 5.5" if "/opus/" in (train_path or "") else "Sonnet 5.5"


def opus_rows():
    """T5 part 6 sessions (Opus 5.5 as the assistant, same 475 cases, order and simulated user) in sim.e5's row
    shape: preds[k] = the answer after k questions, carried forward once the session stops. No turn records, so the
    turn columns show "-"."""
    out = []
    for r in load_rows(OPUS_SESSIONS):
        d = [t["response"]["du_doan"] for t in sorted(r["turns"], key=lambda t: t["turn"])]
        out.append({"model": OPUS, "case": r["story_id"], "kich_ban": r["scenario"], "nhom": r["group"],
                    "n_asked": r["n_asked"], "preds": [d[min(k, len(d) - 1)] for k in range(K + 1)], "usd": 0})
    return out


def rule(rs, fl, scen, n_cases):
    if len({r["case"] for r in rs}) < n_cases:
        return "not evaluable (partial run)"
    s, f = score(rs, scen), score(fl, scen)
    fp_max = int(f["fp"]["k"] + 0.05 * f["fp"]["n"])
    ok = (s["kb3"]["p"] >= f["kb3"]["p"] - 0.05, s["miss"]["k"] <= f["miss"]["k"], s["fp"]["k"] <= fp_max)
    return ("**met**" if all(ok) else "**not met**") + (
        f" (correct {100 * s['kb3']['p']:.1f}% vs >= {100 * f['kb3']['p'] - 5:.1f}%: {'ok' if ok[0] else 'no'}; "
        f"scam called ordinary {s['miss']['k']} vs <= {f['miss']['k']}: {'ok' if ok[1] else 'no'}; "
        f"ordinary flagged {s['fp']['k']} vs <= {fp_max}: {'ok' if ok[2] else 'no'})")


def asked_table(L, runs, names, tr):
    """Questions per session (n_asked) for every model, and how often the model asks again once it has asked once;
    the same counts in each run's training file (rows grouped by story; a question = a non-empty `cau_hoi`)."""
    L += ["## Questions per session\n",
          "\"Asks again\" = sessions with 2 or more questions, out of the sessions with at least 1.\n",
          "| Model | 0 questions | 1 | 2 | 3 | Mean | Asks again after one answer |", "|---|---|---|---|---|---|---|"]

    def row(name, counts):
        n = sum(counts.values())
        once = sum(v for k, v in counts.items() if k >= 1)
        again = sum(v for k, v in counts.items() if k >= 2)
        L.append(f"| {name} | " + " | ".join(fmt(rate(counts.get(k, 0), n)) for k in range(K + 1))
                 + f" | {sum(k * v for k, v in counts.items()) / n:.2f} | {fmt(rate(again, once))} |")
    for m, rs in runs.items():
        row(names[m], Counter(r["n_asked"] for r in rs))
    for name, t in tr.items():
        p = ROOT / t.get("train", "")
        if not p.is_file():
            continue
        by = defaultdict(int)
        for r in load_rows(p):
            by[r["story_id"]] += bool(json.loads(r["messages"][1]["content"])["cau_hoi"])
        row(f"training file of {name} (`{t['train']}`, {len(by)} stories)", Counter(by.values()))
    L.append("")


def missed_dialogues(L, rs, name, by_id, nhom):
    """The full dialogue of every scam case rs called ordinary: the opening, then per turn the model's answer and
    question and the simulated user's reply."""
    missed = sorted((r for r in rs if r["nhom"] == "lua_dao" and is_ordinary(r["preds"][K], nhom)),
                    key=lambda r: r["case"])
    L.append(f"### Dialogues of the scams {name} called ordinary\n")
    for r in missed:
        c = by_id[r["case"]]
        users = [h["text"] for h in r["history"] if h["role"] == "user"]
        L += [f"**`{r['case']}`**: scenario {tag(r['kich_ban'])}, account `{account(c)}`, persona "
              f"`{r.get('tinh_cach', '?')}`, final `{r['preds'][K]}` after {r['n_asked']} question(s)\n",
              f"- Opening: {users[0]}"]
        for i, t in enumerate(r["turns"]):
            q = f": {t['cau_hoi']}" if t["cau_hoi"] else " (stop)"
            L.append(f"- Turn {i}: `{t['du_doan']}`{q}")
            if t["cau_hoi"] and i + 1 < len(users):
                L.append(f"  - User: {users[i + 1]}")
        L.append("")


def main():
    scen, nhom, cases, by_id = load_all()
    raw = load_rows(OUT / "sessions.jsonl")
    meta = json.loads((OUT / "meta.json").read_text()) if (OUT / "meta.json").exists() else {"runs": {}}
    tr = meta["runs"]
    ADAPTERS = {PREFIX + n: n for n in sorted(tr.keys() | {r["model"][len(PREFIX):] for r in raw})}
    SHORT = {QWEN: "untrained", FLASH: "flash-lite", OPUS: "Opus 5.5 teacher",
             **{m: f"LoRA {v}" + (f" ({teacher(tr[v].get('train'))} data)" if v in tr else "")
                for m, v in ADAPTERS.items()}}
    ad = {m: [r for r in raw if "preds" in r and r["model"] == m] for m in ADAPTERS}
    errors = {m: sum("error" in r and r["model"] == m for r in raw) for m in ADAPTERS}
    base = [r for r in load_rows(e12.OUT / "sessions.jsonl") if "preds" in r and r["model"] == QWEN]
    fl = flash_rows()
    op = opus_rows()
    any_run = next(iter(tr.values()), {})

    L = ["# E13 - LoRA fine-tune of Qwen3-4B-Instruct-2507 as the chat model\n",
         "Brief: `docs/tasks/E13-chat-lora-qwen3-4b.md`. Training: `python -m e1.chat_lora`; server driver "
         "`scripts/e13_run.sh`; report `python3 -m e6.e13_report`. Rates as k/n [Wilson 95%]; one run per adapter.\n",
         "## Spend\n", "| Part | USD | Cap |", "|---|---|---|"]
    for m, v in ADAPTERS.items():
        L.append(f"| Gemini (`{FLASH}`, simulated user), part C {v} ({len(ad[m])} sessions) | "
                 f"{run_facts(ad[m])['victim_usd']:.4f} | {CAP} |")
    L += ["\nTraining and serving on the company server's RTX 4060 Ti 16 GB: no API cost.\n",
          "## Part B - training\n",
          f"Base `{any_run.get('base', '?')}` revision `{any_run.get('revision', '?')}`, bf16, frozen. Teacher dialogues "
          "on the T5 stories, never the test sets (files, rows and hash per run below); no row truncated (a row longer "
          f"than the maximum length stops the run). LoRA on {', '.join(any_run.get('target_modules', []))}, alpha = rank, "
          f"dropout 0, AdamW lr {any_run.get('lr', '?')}, weight decay {any_run.get('weight_decay', '?')}, warmup "
          f"{any_run.get('warmup', '?')} then linear decay to 0 over the run, batch 1 x "
          f"{any_run.get('grad_accum', '?')}, seed {any_run.get('seed', '?')}, loss on the assistant JSON only; "
          f"{any_run.get('versions', '?')}. Gradient checkpointing on: without it the first example ran out of memory "
          "on the 16 GB card (2026-11-26 test, no step finished).\n",
          "| Run | Teacher | Train / val file (rows) | sha256 | Longest row / max length (tokens) | Rank | Epochs (steps) "
          "| Trainable params | s/step (incl. val) | Wall h | Peak VRAM allocated / reserved | Chosen epoch (lowest val "
          "loss) | Adapter |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, t in tr.items():
        best = t.get("best_epoch_by_val_loss")
        mb = next((e["adapter_mb"] for e in t.get("epochs_done", []) if e["epoch"] == best), "?")
        tf, vf = t.get("train", "data/T5/train.jsonl"), t.get("val", "data/T5/val.jsonl")
        L.append(f"| {name} | {teacher(tf)} | `{tf}` ({t['train_rows']}) / `{vf}` ({t['val_rows']}) | "
                 f"`{t['data_hash'][:12]}` | {t['longest_row_tokens']:,} / {t['max_len']:,} | {t['rank']} | "
                 f"{t['epochs']} ({t['steps']}) | {t['trainable_params'] / 1e6:.1f}M | {t['wall_s'] / t['steps']:.1f} | "
                 f"{t['wall_s'] / 3600:.2f} | {t['peak_vram_mib']:,} / {t['peak_reserved_mib']:,} MiB | {best} | "
                 f"`.cache/e13/lora/{name}/epoch-{best}` ({mb} MB) |")
    for name, t in tr.items():
        if t.get("train") in DATA_NOTES:
            L.append(f"\n{name} data: {DATA_NOTES[t['train']]}")
    L += ["", "| Run | Epoch | Train loss | Val loss | Train minutes | Val minutes |", "|---|---|---|---|---|---|"]
    for name, t in tr.items():
        for e in t.get("epochs_done", []):
            L.append(f"| {name} | {e['epoch']} | {e['train_loss']:.4f} | {e['val_loss']:.4f} | {e['train_minutes']} | "
                     f"{e['val_minutes']} |")
    L.append("\nTrain loss = mean of the per-step losses of the epoch (each the mean over 16 examples of the "
             "per-token loss); val loss = token-weighted over all val rows of that run's own val file, so val losses "
             "of runs on different teacher data are not comparable.\n")

    runs = {QWEN: base, **ad, FLASH: fl, OPUS: op}
    runs = {m: rs for m, rs in runs.items() if rs}
    ids = set.intersection(*({r["case"] for r in rs} for rs in runs.values()))
    runs = {m: [r for r in rs if r["case"] in ids] for m, rs in runs.items()}
    names = {m: f"{SHORT[m]}" for m in runs}
    L += ["## Part C - test set v2\n",
          "Each chosen adapter on the bf16 base in vLLM (`--enable-lora`), protocol identical to E12 and T6 part C "
          "(`--cases sim/cases_v2 --order-seed 20261128`, `tu_do` prompt unchanged, at most 3 questions, simulated "
          "user `gemini-3.5-flash-lite` with `VICTIM_PROMPT_VIEC`, greedy, JSON schema enforced, one run).\n",
          "| Adapter | Sessions | Errors | Peak VRAM serving (whole card) | Longest prompt | `<think>` in a session | "
          "s/turn mean / p90 | Declared rule (vs flash-lite) |", "|---|---|---|---|---|---|---|---|"]
    for m, v in ADAPTERS.items():
        f = run_facts(ad[m])
        vram = tr.get(v, {}).get("serving", {}).get("vram_peak_mib", "?")
        L.append(f"| {v} | {len(ad[m])} | {errors[m]} | {vram} MiB | {f['longest_prompt']:,} | {f['think']} | "
                 f"{f['secs'][0]:.2f} / {f['secs'][2]:.2f} | {rule(ad[m], fl, scen, len(cases))} |")
    if len(ids) < len(cases):
        L.append(f"\n**Rows below are on the {len(ids)} cases every model ran** (a run stopped early).")
    L.append("\nThe Opus 5.5 teacher row is T5 part 6 (`experiments/T5/test_v2_opus.md`): the same 475 cases, order and "
             "simulated user, with Opus 5.5 as the assistant. Its sessions keep no turn records, so its turn columns "
             "show \"-\".")
    L.append("")
    main_tables(L, runs, names, scen, by_id)
    L += [f"### `{CHUA_DU}` after {K} questions, by group\n",
          "Minh counts `chua_du_can_cu` on an ordinary transfer as a safe outcome; Run B's training data keeps the "
          "ordinary sessions the teacher ended with it, so this run may give it more often.\n",
          "| Model | All | Scam | Ordinary |", "|---|---|---|---|"]
    for m, rs in runs.items():
        cd = [r for r in rs if r["preds"][K] == CHUA_DU]
        n_s = sum(r["nhom"] == "lua_dao" for r in rs)
        L.append(f"| {names[m]} | {fmt(rate(len(cd), len(rs)))} | "
                 f"{fmt(rate(sum(r['nhom'] == 'lua_dao' for r in cd), n_s))} | "
                 f"{fmt(rate(sum(r['nhom'] == 'binh_thuong' for r in cd), len(rs) - n_s))} |")
    L.append("")
    L.append("## Paired comparisons on the same cases\n")
    for i, m in enumerate(ADAPTERS):
        if m in runs:
            for other in [QWEN, FLASH, OPUS, *list(ADAPTERS)[:i]]:
                if other in runs:
                    paired_pair(L, runs[m], runs[other], SHORT[m], SHORT[other], by_id, nhom)
    account_rule_table(L, runs, names, by_id, nhom)
    per_scenario_table(L, runs, names, nhom)
    for m in ADAPTERS:
        if m in runs:
            missed_table(L, runs[m], SHORT[m], {SHORT[o]: runs[o] for o in (QWEN, FLASH, OPUS) if o in runs}, by_id,
                         nhom)
            missed_dialogues(L, runs[m], SHORT[m], by_id, nhom)
    asked_table(L, runs, names, tr)
    q = {m: sum(r["n_asked"] for r in rs) / len(rs) for m, rs in runs.items()}
    L += ["## Limits\n",
          "- Stories, the teachers (Claude Sonnet 5.5, Opus 5.5) and the simulated users are all LLM-written.",
          "- The teachers ask about 1 question per session (Sonnet 1.23, Opus 0.95 on this set); flash-lite asks 0.36. "
          "Questions per session here: " + ", ".join(f"{SHORT[m]} {v:.2f}" for m, v in q.items()) + ".",
          "- The 45 cases rewritten in T6 part A2 are easy by construction; see the rows without them.",
          f"- One run per adapter; checkpoints chosen by validation loss only. Answer after {K} questions is scored.\n"]
    (OUT / "report.md").write_text("\n".join(L), encoding="utf-8")
    print("report:", (OUT / "report.md").relative_to(ROOT))


if __name__ == "__main__":
    main()
