"""Real Gemini API spend so far, recomputed from the raw records (read-only, offline, no API call).

    .venv/bin/python scripts/gemini_spend.py

Sources (every one read here, nothing taken from report text except the comparison column):
- data/E1/runs, data/E1b/runs, data/E1b/gen/runs, data/E1b/web_runs: `B__`/`C__` dirs written by e1/vlm.py. These
  records have tokens but no USD; USD is recomputed with e1.score.PRICES, output = candidates + thinking tokens
  (vlm.py stores them apart).
- every `*runs/<config>/*.json` written by e1/e4_run.py (has a `usd` key): recorded USD (core.llm, same prices).
- data/E1b/gen/calls.jsonl, data/E1b/gen_ref/calls.jsonl: one line per image-model call (e1/gen_nb.py).
- data/E4/gen_cost.json: paraphrase pool for the E4 training renders (e1/gen_train.py). `usd` is the running total
  of all processes; `usd_this_process` is a part of it and is not added again.
- data/E6/cost.json: E6 training stories (sim/e6_data.py). Running total from llm.USAGE, retries included.
- sim/cases/*.json `sinh_boi.usd`: opening messages; cases 0-4 per scenario are E2 (`v1`), 5-19 are E5.
- experiments/E2/sessions.jsonl, experiments/E2/run1/sessions.jsonl: assistant (`usd`) and simulated user
  (`victim_usd`), both gemini-3.5-flash-lite (sim.run default model and VICTIM_MODEL).
- experiments/E5/sessions.jsonl: assistant `usd` by `model`; `victim_usd` is always gemini-3.5-flash-lite.
Writes experiments/E10/spend.md and experiments/E10/spend.json.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from e1.gen_nb import MODEL as IMG_MODEL, PRICE_IMG_OUT, PRICE_IN, PRICE_TEXT_OUT  # noqa: E402
from e1.score import PRICES  # noqa: E402  USD per 1M tokens (input, output incl. thinking)

OUT = ROOT / "experiments/E10"
VICTIM = "gemini-3.5-flash-lite"
E2_ASSISTANT = "gemini-3.5-flash-lite"  # E2 rows carry no model; sim.run used the default model (E2 report)
PER_SCENARIO = 5  # sim/cases.py: cases 0-4 of each scenario are the E2 (v1) set
# Totals as printed in the reports, for the comparison only (Gemini rows; read 2026-11-23)
REPORTED = {
    "E4": ("experiments/E4/report.md section 7: carbon 3.81 + 3.8-flash@low 0.25 + flash-lite 0.23 + paraphrase "
           "0.28 + gen_ref images 9.07", 3.81 + 0.25 + 0.23 + 0.28 + 9.07),
    "E5": ("experiments/E5/report.md cost table, Gemini assistants + every simulated user + openings 0.059",
           0.331 + 0.054 + 0.244 + 0.021 + 2.150 + 0.029 + 0.022 + 0.208 + 0.200 + 0.058 + 0.059),
    "E6": ("experiments/E6/report.md: 660 calls, 1.23 USD", 1.23),
    "E1b": ("experiments/E1b/report.md: gen images 2.58 USD (reading cost not totalled there)", 2.58),
    "E2": ("experiments/E2/report.md: final run 0.45 USD (assistants, simulated user, openings)", 0.45),
}
PLANNER = 18.2  # planner's sum of the E4, E5, E6 reports (docs/tasks/E10-chat-models-and-image-flow.md)

rows: dict[tuple, dict] = {}  # (experiment, purpose, model, how) -> {usd, records, source}
stats = defaultdict(int)  # counters for the caveats


def is_gemini(model: str) -> bool:
    return model.split("@")[0].startswith("gemini-")


def add(exp, purpose, model, usd, source, how, n=1):
    r = rows.setdefault((exp, purpose, model, how), {"usd": 0.0, "records": 0, "sources": set()})
    r["usd"] += usd
    r["records"] += n
    r["sources"].add(source)


def token_usd(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES[model.split("@")[0]]
    return (tin * pin + tout * pout) / 1e6


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


# ---- per-image read runs (E1, E1b, E4)
RUN_SETS = {"data/E1/runs": "E1", "data/E1b/runs": "E1b", "data/E1b/gen/runs": None, "data/E1b/web_runs": None,
            "data/E1b/gen_ref/runs": "E4", "data/E4/val/runs": "E4", "data/E4/val_la/runs": "E4"}
for d, exp in RUN_SETS.items():
    base = ROOT / d
    if not base.exists():
        continue
    for cfg in sorted(base.iterdir()):
        files = sorted(cfg.glob("*.json"))
        for f in files:
            j = json.loads(f.read_text(encoding="utf-8"))
            model = j.get("model")
            if not model or model.startswith("local:"):
                continue  # OCR tools and self-hosted models: no API cost
            if "error" in j:
                stats["read_error_records"] += 1
                continue
            if "usd" in j:  # e1/e4_run.py via core.llm: tokens_out already includes thinking
                how = "recorded usd (e4_run)"
                usd = j["usd"]
                if is_gemini(model):
                    stats["e4_recompute_gap"] += abs(usd - token_usd(model, j["tokens_in"], j["tokens_out"]))
                stats["retries_unbilled_in_record"] += j.get("retries", 0)
                # gen and web are E4 sets (the E1b B runs on them use the vlm.py format below)
                e = exp or "E4"
                purpose = f"read images ({j.get('set', cfg.parent.parent.name)})"
            else:  # e1/vlm.py: tokens_out excludes thinking
                how = "recomputed from tokens (e1.score.PRICES)"
                usd = token_usd(model, j["tokens_in"], j["tokens_out"] + j.get("tokens_thought", 0))
                stats["retries_unbilled_in_record"] += j.get("attempts", 1) - 1
                e = exp or "E1b"
                purpose = f"read images, method {j.get('method', cfg.name[0])} ({base.relative_to(ROOT / 'data')})"
            add(e, purpose, model, usd, rel(cfg), how)

# ---- image generation (gemini-nano-banana-2.1)
for d, exp, purpose in (("data/E1b/gen", "E1b", "generate 40 `gen` images"),
                        ("data/E1b/gen_ref", "E4", "generate 150 `gen_ref` images")):
    p = ROOT / d / "calls.jsonl"
    for line in p.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        recomputed = c["tokens_in"] * PRICE_IN + c["tokens_img"] * PRICE_IMG_OUT + max(0, c["tokens_text"]) * PRICE_TEXT_OUT
        stats["img_recompute_gap"] += abs(c["usd"] - recomputed)
        stats["img_calls_no_image"] += not c.get("got_image", True)
        add(exp, purpose, c.get("model_version") or IMG_MODEL, c["usd"], rel(p), "recorded usd per call (gen_nb)")

# ---- running-total cost files
gc = json.loads((ROOT / "data/E4/gen_cost.json").read_text(encoding="utf-8"))
stats["gen_cost_entries_gap"] = abs(gc["usd"] - sum(e["usd"] for e in gc["entries"]))
add("E4", "paraphrase pool for training renders", gc["model"], gc["usd"], "data/E4/gen_cost.json",
    "running total `usd` (not `usd_this_process`)", gc["calls"])
e6 = json.loads((ROOT / "data/E6/cost.json").read_text(encoding="utf-8"))
stats["e6_recompute_gap"] = abs(e6["usd"] - token_usd(e6["model"], e6["tokens_in"], e6["tokens_out"]))
add("E6", "training stories (sim/e6_data.py)", e6["model"], e6["usd"], "data/E6/cost.json",
    "running total `usd`, retries included", e6["calls"])

# ---- opening messages
for p in sorted((ROOT / "sim/cases").glob("*.json")):
    c = json.loads(p.read_text(encoding="utf-8"))
    s = c.get("sinh_boi") or {}
    exp = "E2" if int(p.stem.rsplit("__", 1)[1]) < PER_SCENARIO else "E5"
    add(exp, "opening messages (sim/cases)", s.get("model", "?"), s.get("usd", 0.0), "sim/cases/*.json",
        "recorded `sinh_boi.usd`")

# ---- chat sessions
for f, label in (("experiments/E2/run1/sessions.jsonl", "chat sessions, run 1"),
                 ("experiments/E2/sessions.jsonl", "chat sessions, final run")):
    for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        add("E2", f"{label}: assistant", E2_ASSISTANT, r.get("usd", 0.0), f, "recorded session `usd`")
        add("E2", f"{label}: simulated user", VICTIM, r.get("victim_usd", 0.0), f, "recorded `victim_usd`")
        stats["session_errors"] += "error" in r
for line in (ROOT / "experiments/E5/sessions.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    stats["session_errors"] += "error" in r
    if not r["model"].startswith("local:"):
        add("E5", "chat sessions: assistant", r["model"], r.get("usd", 0.0), "experiments/E5/sessions.jsonl",
            "recorded session `usd`")
    add("E5", f"chat sessions: simulated user (assistant {r['model']})", VICTIM, r.get("victim_usd", 0.0),
        "experiments/E5/sessions.jsonl", "recorded `victim_usd`")

# ---- totals
table = sorted(({"experiment": k[0], "purpose": k[1], "model": k[2], "how": k[3], "usd": round(v["usd"], 4),
                 "records": v["records"], "sources": sorted(v["sources"]), "gemini": is_gemini(k[2])}
                for k, v in rows.items()), key=lambda r: (r["experiment"], not r["gemini"], r["purpose"], r["model"]))
gem = [r for r in table if r["gemini"]]
other = [r for r in table if not r["gemini"]]
total = sum(r["usd"] for r in gem)
by_exp, by_model = defaultdict(float), defaultdict(float)
for r in gem:
    by_exp[r["experiment"]] += r["usd"]
    by_model[r["model"].split("@")[0]] += r["usd"]
e4e5e6 = by_exp["E4"] + by_exp["E5"] + by_exp["E6"]
e1b_images = sum(r["usd"] for r in gem if r["experiment"] == "E1b" and r["model"] == IMG_MODEL)
e1_pricey = sum(r["usd"] for r in gem if r["experiment"] == "E1" and r["model"] != "gemini-3.5-flash-lite")
e1_b = sum(r["usd"] for r in gem if r["experiment"] == "E1" and "method B" in r["purpose"])

caveats = [
    f"Comparison with the planner's ~{PLANNER} USD (E4 + E5 + E6 report tables): those three experiments sum to "
    f"{e4e5e6:.2f} USD here, matching the reports to the cent. The all-time total is higher because E1, E1b and E2 "
    f"also spent Gemini money and were not in the planner's sum: E1 {by_exp['E1']:.2f} (180 images x 2 methods x "
    f"3 models; 3.8-flash and 4-carbon alone {e1_pricey:.2f}), E1b "
    f"{by_exp['E1b']:.2f} (2.58 for the 40 `gen` images, the rest flash-lite reads), E2 {by_exp['E2']:.2f} (the "
    "report's 0.45 is the final run only; the kept run 1 in experiments/E2/run1 adds the rest).",
    f"Cap scope: plan section 7 (2026-11-22) put the 20 USD cap on 'E4, E5, E6 and generated images'. In that "
    f"scope the spend is {e4e5e6:.2f} USD, or {e4e5e6 + e1b_images:.2f} USD if the E1b `gen` images (made "
    f"2026-11-20, before the cap) count. If the 25 USD cap means all-time spend, it is already passed "
    f"({total:.2f} USD). Which scope applies is Minh's call.",
    "E1 and E1b `B__`/`C__` read runs (e1/vlm.py) store tokens but no USD: recomputed with e1.score.PRICES (the "
    "2026-11-20 list prices, intro prices for 3.8-flash and 4-carbon), output = candidates + thinking tokens.",
    f"Per-record USD covers only the attempt that was kept. Earlier attempts that returned malformed JSON were "
    f"billed but not recorded: {stats['retries_unbilled_in_record']} such extra attempts across all read runs "
    "(rate-limit and 5xx errors are not billed, so this is an upper bound on missing calls, not a count). The "
    "same holds for chat sessions (sim/run.py sums only the kept calls). Cost files (E4 gen_cost.json, E6 "
    "cost.json) and image calls.jsonl count every call.",
    "Cross-check against the laptop run logs (.cache/logs, llm.USAGE, every billed call incl. malformed retries): "
    "the gen_ref flash-lite read is 0.2329 USD in the log and in the raw records; the 4-carbon logs (1.7075 + "
    "1.7243) and 3.8-flash@low log (0.2011) cover only some invocations, so they are lower than the raw sums.",
    f"Read records with an error ({stats['read_error_records']}) carry no tokens; e4_run.py does not write failed "
    "closed-model images at all (they were rerun), so their failed calls are not recorded.",
    "Not recorded anywhere (excluded from the total): sim/fill_eval.py (E2 `dien_bang` fill measurement, "
    "experiments/E2/fill_openings.json: 2 prompts x 75 openings = 150 flash-lite calls, plus `--dev` tuning "
    "runs on tests/fill_dev.json); E2 sessions deleted by `sim.run --fresh` before run 1 and between runs; any "
    "manual smoke calls and app trials (core/dialog.py, core/vision.py log no cost; data/app/app.sqlite has no "
    "sessions). [inference] One fill call costs about 0.0003 USD (an E2 session with 0 questions, fill + "
    "conclusion, is ~0.0006 USD), so fill_eval is well under 0.1 USD.",
    "[inference] experiments/E1/report_B_only.md looks like the provisional B-only scoring of the same runs "
    f"(findings.md 2026-11-20); if the B runs were instead deleted and redone, that first pass (up to {e1_b:.2f} USD "
    "for all three models) is missing here.",
    "E2 rows carry no model name: counted as gemini-3.5-flash-lite (sim.run default; E2 report says so).",
    f"Self-checks: recorded vs token-recomputed USD differ by {stats['e4_recompute_gap']:.6f} (e4_run Gemini records), "
    f"{stats['img_recompute_gap']:.6f} (image calls), {stats['e6_recompute_gap']:.6f} (E6 cost.json); "
    f"gen_cost.json `usd` vs sum of its entries differ by {stats['gen_cost_entries_gap']:.6f}. "
    f"Image calls that returned no image (billed anyway): {stats['img_calls_no_image']}.",
    "Prices: 4-carbon and 3.8-flash are intro prices; spend is what was billed at the time, not today's price.",
]

# ---- print
print(f"{'exp':4} {'model':26} {'USD':>8} {'n':>6}  purpose")
for r in gem:
    print(f"{r['experiment']:4} {r['model']:26} {r['usd']:8.4f} {r['records']:6}  {r['purpose']}")
print("\nby experiment:", {k: round(v, 3) for k, v in sorted(by_exp.items())})
print("by model:", {k: round(v, 3) for k, v in sorted(by_model.items())})
for k, (src, v) in REPORTED.items():
    print(f"  {k}: raw {by_exp[k]:.3f} vs report {v:.3f} ({src})")
print("non-Gemini:", [(r["experiment"], r["model"], r["usd"]) for r in other if r["usd"]])
print(f"\nGEMINI TOTAL {total:.2f} USD (E4+E5+E6 {e4e5e6:.2f}; planner ~{PLANNER})")

# ---- write
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "spend.json").write_text(json.dumps({
    "gemini_total_usd": round(total, 4), "e4_e5_e6_usd": round(e4e5e6, 4), "planner_estimate_usd": PLANNER,
    "by_experiment": {k: round(v, 4) for k, v in sorted(by_exp.items())},
    "by_model": {k: round(v, 4) for k, v in sorted(by_model.items())},
    "reported": {k: {"usd": round(v, 4), "source": s} for k, (s, v) in REPORTED.items()},
    "rows": gem, "non_gemini_rows": other, "caveats": caveats}, ensure_ascii=False, indent=1), encoding="utf-8")

L = ["## Gemini spend so far", "",
     f"**All-time Gemini total: {total:.2f} USD.** E4 + E5 + E6 (the planner's ~{PLANNER} USD scope): "
     f"{e4e5e6:.2f} USD; with the E1b `gen` images: {e4e5e6 + e1b_images:.2f} USD. Against the 25 USD cap that "
     f"leaves {25 - e4e5e6:.2f} / {25 - e4e5e6 - e1b_images:.2f} USD in the capped scope, or nothing "
     f"({25 - total:.2f}) if the cap is all-time (see caveat 2). Recomputed from the raw records by "
     "`scripts/gemini_spend.py` (no report text used); machine-readable copy in `spend.json`.", "",
     "| Experiment | Raw records (USD) | Report figure (USD) |", "|---|---|---|"]
for k in sorted(by_exp):
    rep = f"{REPORTED[k][1]:.2f}" if k in REPORTED else "none"
    L.append(f"| {k} | {by_exp[k]:.2f} | {rep} |")
L += ["", "| Model | USD |", "|---|---|"] + [f"| `{m}` | {v:.2f} |" for m, v in sorted(by_model.items())]
L += ["", "| Experiment | Purpose | Model | USD | Records | How counted |", "|---|---|---|---|---|---|"]
L += [f"| {r['experiment']} | {r['purpose']} | `{r['model']}` | {r['usd']:.4f} | {r['records']} | {r['how']} |"
      for r in gem]
L += ["", "Non-Gemini spend (not in the total): "
      + ("; ".join(f"{r['experiment']} {r['purpose']} `{r['model']}` {r['usd']:.3f} USD" for r in other if r["usd"])
         or "none") + ".", "", "### Caveats", ""] + [f"- {c}" for c in caveats]
(OUT / "spend.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"wrote {rel(OUT / 'spend.md')}, {rel(OUT / 'spend.json')}")
