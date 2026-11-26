# E12 - Untrained `Qwen3-4B-Instruct-2507` as the chat model, on test set v2

From: planner tab `Momo_TechContest`. For: `code` tab. Rewritten 2026-11-26 for the 25-scenario catalogue and test
set v2 (the version of the morning of 2026-11-26 is replaced). Minh approved the step; it runs on the company
server. Starts on "E12 go".

## Question

Minh will fine-tune one open text-only chat model, `Qwen/Qwen3-4B-Instruct-2507` (E13). Where does it start,
untrained, on test set v2, next to `gemini-3.5-flash-lite` (T6: correct scenario 419/475, scam called ordinary
18/225, ordinary flagged 2/250, 0.36 questions per session)?

## Run

- Model `Qwen/Qwen3-4B-Instruct-2507` (8.0 GB, Apache-2.0, revision `cdbee75f17` or the current one; write down which),
  unquantised, served by vLLM on `intern-remote.ownego.com` as in E10 part A. No thinking mode in this build; still
  check that no turn contains `<think>`.
- Protocol identical to T6 Part C, so the rows pair case by case: `python -m sim.e5 --cases sim/cases_v2 --order-seed
  20261128`, `tu_do` prompt and 25-scenario catalogue unchanged, at most 3 questions, simulated user
  `gemini-3.5-flash-lite` with `VICTIM_PROMPT_VIEC`, greedy decoding, JSON schema enforced, one run, no rerun to
  pick a number.
- The first-turn prompt is about 3,300 tokens (Qwen3 tokenizer, planner's count on 2026-11-26) and grows with the
  dialogue: set the vLLM context length to at least 8,192 and report the longest prompt seen.
- Server rules: `nvidia-smi` and `df -h` first. The disk is nearly full: if fewer than 12 GB are free before the
  download, stop and tell the planner (delete nothing to make room). Never kill another user's job, never restart a
  download in progress, delete nothing outside `~/pretransfer-scam-assistant`.
- Money: only the simulated user costs money (T6 Part C: 0.052 USD for 169 questions). `--cap-usd 0.35`,
  `--project-after 50` (the seeded order puts 2 cases of each scenario in the first 50). If the projection exceeds
  the cap, stop at those 50 and report them. Never raise a cap yourself.
- No other model, no prompt change, no training, no C0 second opinion (dropped after T6).

## Report

One row for `qwen3-4b-instruct-2507` next to the T6 flash-lite row, columns in Minh's order of priority:

1. scam called ordinary (k/225);
2. ordinary flagged as scam (k/250);
3. correct scenario after 0 to 3 questions;
4. `chua_du_can_cu`, questions asked, malformed turns, seconds per turn (mean, p90).

Every rate as k/n with a 95% Wilson interval; the same rows split by group, by account label and by group x label,
and per scenario. Also:

- paired against `gemini-3.5-flash-lite` on the same 475 cases: 2x2 right/wrong table, McNemar, paired bootstrap
  interval, for correct scenario and for scam called ordinary;
- the same main rows on the 430 cases not rewritten by T6 Part A2 (the 45 rewritten ones are easy by construction);
- one reference row per model with the account rule applied after the model: an ordinary conclusion becomes
  "caution" when the account label is not `moi`, or when the name does not match and the conclusion is not
  `bt_tra_shipper_khi_nhan_hang`. Mark it "rule chosen by the planner on this test set" (flash-lite: 2/225 scams
  still called ordinary, 41/250 ordinary moved to caution);
- every scam case called ordinary: case id, scenario, account label, answer, number of questions, opening;
- peak VRAM, weight size, load time, licence, revision.

No rule is declared: this run describes the untrained starting point. It does not decide the live chat model.

## Deliverables

- `experiments/E12/report.md` (English), real spend at the top; sessions in `experiments/E12/sessions.jsonl`.
- A short E12 section in `EXPERIMENTS.md` and a row in its overview table. Commit and push.
- Free the GPU, keep the weights (E13 trains on them), report `du -sh .cache/hf` and `df -h`.
- One line to the planner tab when done, or at once when the disk check or the projection rule stops the run.
