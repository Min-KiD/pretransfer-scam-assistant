# E12 - Untrained `Qwen3-4B-Instruct-2507` as the chat model

From: planner tab `Momo_TechContest`. For: `code` tab. Written 2026-11-26.

**Status: not a go yet.** Do not start until the planner tab sends "E12 go".

## Question

Minh wants to fine-tune one open text-only chat model and asked for a quick untrained baseline of Qwen3-4B first, to see which base is worth the fine-tune. The two 4B Qwen models measured so far (`qwen3-vl-4b` 73.7%, `qwen3.5-4b` 69.3%) are vision models. How does the text-only `Qwen/Qwen3-4B-Instruct-2507` do on the same 300 sessions, next to `gemma-4-e4b-qat` (77.0%, 18 of 220 scams called ordinary)?

Why this build and not `Qwen/Qwen3-4B`: it is the newer release of the same size (Hugging Face, checked 2026-11-26: both 8.0 GB, Apache-2.0, not gated; `Instruct-2507` revision `cdbee75f17`), it has no thinking mode, and it ranked first after fine-tuning in a public 12-model benchmark (distil labs, 2025-12-10).

## Run

- Same protocol as E5 and E10 part A: the 300 cases, the `tu_do` prompt unchanged, simulated user `gemini-3.5-flash-lite`, greedy decoding, JSON schema enforced, one run, no reruns to pick a number.
- Model `Qwen/Qwen3-4B-Instruct-2507`, unquantised, served by vLLM on the server as in E10 part A. Keep `enable_thinking: false` in the request as for the other Qwen models; check that no turn contains `<think>`.
- Server rules as always: `nvidia-smi` first, never kill another user's job, never restart a download in progress, delete nothing outside `~/pretransfer-scam-assistant`.
- **Case order.** `sim.e5` runs cases in id order, which made the first 30 sessions of E11 useless. Before this run, add a seeded stratified order to `sim.e5` (flag, default off so old runs reproduce): seed `20261126`, round-robin over the 15 scenarios, so that **the first 60 sessions hold exactly 4 cases of each scenario (44 scam, 16 ordinary)**. Write the seed and the first 60 case ids into the report.
- **Money.** Only the simulated user costs money (E10 part A: 0.16-0.22 USD per open model for 300 sessions). `--cap-usd 0.35`, `--project-after 60`. If the projection after 60 sessions exceeds the cap, stop at those 60 and report them. Gemini cap scope (E4 to E12): 24.27 of 25 USD spent before this run. Never raise a cap yourself.
- No other model, no prompt change, no training.

## Report

One row for `qwen3-4b-instruct-2507` next to the existing 300-session rows (`gemini-3.5-flash-lite`, `claude-haiku-5-5`, `gemma-4-e4b-qat`, `qwen3-14b-awq`, `qwen3-8b-fp8`, `qwen3-vl-4b`, `qwen3.5-4b`), columns in Minh's order of priority:

1. scam called ordinary (k/220);
2. ordinary flagged as scam (k/80);
3. correct scenario after 0-3 questions;
4. `chua_du_can_cu`, questions asked, malformed turns, seconds per turn (mean, p90).

Every rate as `k/n` with a 95% Wilson interval. Also:

- paired against `gemma-4-e4b-qat` and against `gemini-3.5-flash-lite` on the same cases: 2x2 right/wrong table, McNemar, paired bootstrap interval, for correct scenario and for scam called ordinary;
- the E6 second opinion (C0) on the sessions: LLM alone vs LLM + C0, share downgraded (CPU, free);
- the list of scam cases still called ordinary (case id, scenario);
- peak VRAM, weight size, load time, licence, revision.

No rule is declared: this run describes the untrained starting point of a fine-tune base. It does not decide the live chat model. Report the usual M2 comparison (5 points behind `gemini-3.5-flash-lite`, 81.3%) for reference only.

## Deliverables

- `experiments/E12/report.md` (English), real spend at the top.
- A short E12 section in `EXPERIMENTS.md` and a row in its overview table. Commit and push.
- Free the GPU, keep the weights, report `du -sh .cache/hf`.
- One line to the planner tab when done, or when stopped by the projection rule.
