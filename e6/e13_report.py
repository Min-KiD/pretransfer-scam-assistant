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

from core.scenarios import ROOT
from e6 import e12_report as e12
from e6.e12_report import (CAP, FLASH, QWEN, account_rule_table, flash_rows, load_all, main_tables, missed_table,
                           paired_pair, per_scenario_table, run_facts)
from sim.e5 import K, load_rows, score

OUT = ROOT / "experiments/E13"
PREFIX = "local:qwen3-4b-e13-"


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


def main():
    scen, nhom, cases, by_id = load_all()
    raw = load_rows(OUT / "sessions.jsonl")
    meta = json.loads((OUT / "meta.json").read_text()) if (OUT / "meta.json").exists() else {"runs": {}}
    tr = meta["runs"]
    ADAPTERS = {PREFIX + n: n for n in sorted(tr.keys() | {r["model"][len(PREFIX):] for r in raw})}
    SHORT = {QWEN: "untrained", **{m: f"LoRA {v}" for m, v in ADAPTERS.items()}, FLASH: "flash-lite"}
    ad = {m: [r for r in raw if "preds" in r and r["model"] == m] for m in ADAPTERS}
    errors = {m: sum("error" in r and r["model"] == m for r in raw) for m in ADAPTERS}
    base = [r for r in load_rows(e12.OUT / "sessions.jsonl") if "preds" in r and r["model"] == QWEN]
    fl = flash_rows()
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
          f"Base `{any_run.get('base', '?')}` revision `{any_run.get('revision', '?')}`, bf16, frozen. Data "
          f"`data/T5/train.jsonl` ({any_run.get('train_rows', '?')} rows) and `val.jsonl` "
          f"({any_run.get('val_rows', '?')} rows), sha256 `{str(any_run.get('data_hash', '?'))[:16]}`; the `*_chua_du` "
          f"files not used. Longest row {any_run.get('longest_row_tokens', '?')} tokens with the model's tokenizer, "
          f"maximum length {any_run.get('max_len', '?')}: no row truncated. LoRA on "
          f"{', '.join(any_run.get('target_modules', []))}, alpha = rank, dropout 0, AdamW lr "
          f"{any_run.get('lr', '?')}, weight decay {any_run.get('weight_decay', '?')}, warmup "
          f"{any_run.get('warmup', '?')} then linear decay to 0 over the run, batch 1 x "
          f"{any_run.get('grad_accum', '?')}, seed {any_run.get('seed', '?')}, loss on the assistant JSON only; "
          f"{any_run.get('versions', '?')}. Gradient checkpointing on: without it the first example ran out of memory "
          "on the 16 GB card (2026-11-26 test, no step finished).\n",
          "| Run | Rank | Epochs (steps) | Gradient checkpointing | Trainable params | s/step (incl. val) | Wall h | "
          "Peak VRAM allocated / reserved | Chosen epoch (lowest val loss) | Adapter |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for name, t in tr.items():
        best = t.get("best_epoch_by_val_loss")
        mb = next((e["adapter_mb"] for e in t.get("epochs_done", []) if e["epoch"] == best), "?")
        ckpt = "on" if t.get("gradient_checkpointing", True) else "off"
        L.append(f"| {name} | {t['rank']} | {t['epochs']} ({t['steps']}) | {ckpt} | {t['trainable_params'] / 1e6:.1f}M | "
                 f"{t['wall_s'] / t['steps']:.1f} | {t['wall_s'] / 3600:.2f} | {t['peak_vram_mib']:,} / "
                 f"{t['peak_reserved_mib']:,} MiB | {best} | `.cache/e13/lora/{name}/epoch-{best}` ({mb} MB) |")
    L += ["", "| Run | Epoch | Train loss | Val loss | Train minutes | Val minutes |", "|---|---|---|---|---|---|"]
    for name, t in tr.items():
        for e in t.get("epochs_done", []):
            L.append(f"| {name} | {e['epoch']} | {e['train_loss']:.4f} | {e['val_loss']:.4f} | {e['train_minutes']} | "
                     f"{e['val_minutes']} |")
    L.append("\nTrain loss = mean of the per-step losses of the epoch (each the mean over 16 examples of the "
             "per-token loss); val loss = token-weighted over all val rows.\n")

    runs = {QWEN: base, **ad, FLASH: fl}
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
    L.append("")
    main_tables(L, runs, names, scen, by_id)
    L.append("## Paired comparisons on the same cases\n")
    for m in ADAPTERS:
        if m in runs:
            for other in (QWEN, FLASH):
                if other in runs:
                    paired_pair(L, runs[m], runs[other], SHORT[m], SHORT[other], by_id, nhom)
    account_rule_table(L, runs, names, by_id, nhom)
    per_scenario_table(L, runs, names, nhom)
    for m in ADAPTERS:
        if m in runs:
            missed_table(L, runs[m], SHORT[m], {SHORT[o]: runs[o] for o in (QWEN, FLASH) if o in runs}, by_id, nhom)
    q = {m: sum(r["n_asked"] for r in rs) / len(rs) for m, rs in runs.items()}
    L += ["## Limits\n",
          "- Stories, the teacher (Claude Sonnet 5.5) and the simulated users are all LLM-written.",
          "- The teacher asks about 1.2 questions per session; flash-lite asks 0.36, so the student is expected to ask "
          "more. Questions per session here: " + ", ".join(f"{SHORT[m]} {v:.2f}" for m, v in q.items()) + ".",
          "- The 45 cases rewritten in T6 part A2 are easy by construction; see the rows without them.",
          f"- One run per adapter; checkpoints chosen by validation loss only. Answer after {K} questions is scored.\n"]
    (OUT / "report.md").write_text("\n".join(L), encoding="utf-8")
    print("report:", (OUT / "report.md").relative_to(ROOT))


if __name__ == "__main__":
    main()
