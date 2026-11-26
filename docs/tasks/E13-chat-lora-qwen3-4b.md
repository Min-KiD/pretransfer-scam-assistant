# E13 - LoRA fine-tune of `Qwen3-4B-Instruct-2507` as the chat model

From: planner tab `Momo_TechContest`. For: `code` tab. Rewritten 2026-11-26 (the earlier version is replaced: its
Part A, teacher dialogues, was done by the `sonnet` tab as T5). Minh approved the step; it runs on the company
server, after E12 has freed the GPU. Starts on "E13 go".

## Question

Does a LoRA adapter trained on Claude Sonnet 5.5 teacher dialogues bring `Qwen/Qwen3-4B-Instruct-2507` to the level
of `gemini-3.5-flash-lite` on test set v2 (T6: correct scenario 419/475, scam called ordinary 18/225, ordinary
flagged 2/250)?

Method fixed by Minh: LoRA only, base weights frozen, full-precision (bf16) base, no quantised base, no rented GPU.

## Data (ready, local, gitignored: copy it to the server)

- `data/T5/train.jsonl`: 3,692 rows, one per assistant turn of 1,702 kept teacher sessions (25 scenarios; half of
  the stories and users by Gemini flash-lite, half by Claude). `data/T5/val.jsonl`: 501 rows of 237 kept sessions.
  Each row: `messages` = [user: the exact `tu_do` prompt of that turn, assistant: compact JSON
  `{"du_doan","cau_hoi"}`], plus `story_id`, `scenario`, `turn`.
- Prompts are 11.2k to 12.7k characters (about 3,300 tokens on the first turn by the planner's earlier count).
  Measure the longest row with the model's tokenizer, set the maximum length from it, report it. No truncation: if a
  row does not fit, stop and tell the planner.
- **Not** in the main runs: `data/T5/train_chua_du.jsonl` and `val_chua_du.jsonl` (ordinary stories the teacher
  ended with `chua_du_can_cu`). Leave them alone.
- Never train or validate on `sim/cases_v2/` or `sim/cases/`. Planner's check on 2026-11-26: 0 of the 2,050 teacher
  openings equal a test opening, 0 pairs above 0.6 word overlap, 0 shared purpose lines.

## Part B - Training

- Same setup as `e1/lora_train.py` (plain `peft`, gradient checkpointing). Adapters on all attention and MLP
  projections (`q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj`). The model's own chat template.
- Fixed: learning rate 2e-4, linear schedule, warmup 5% of steps, effective batch 16 (start with batch 1 x 16
  accumulation), dropout 0, weight decay 0.01, alpha = rank, loss on the assistant message only, seed 3407,
  3 epochs with a checkpoint and a validation loss after each.
- Two runs only: rank 16, then rank 64.
- **Timing gate.** After the first 50 optimiser steps of rank 16, project the time of the full run and send the
  planner one line (seconds per step, projected hours, peak VRAM). Go on without waiting if the projection is under
  8 hours per run; otherwise stop and wait.
- Out of memory, or the card taken by another user: stop and tell the planner. Do not switch to a 4-bit base, do
  not shorten the prompt, do not kill anyone's job.
- Pick one checkpoint per rank by validation loss. Report train and validation loss per epoch, trainable
  parameters, peak VRAM, minutes per epoch, adapter size.

## Part C - Evaluation

- Serve the bf16 base with each chosen adapter through vLLM. Protocol identical to E12 and T6 Part C (`--cases
  sim/cases_v2 --order-seed 20261128`, `tu_do` prompt unchanged, simulated user `gemini-3.5-flash-lite`, greedy,
  JSON schema enforced, one run per adapter, no rerun to pick a number).
- Gemini: `--cap-usd 0.35` per adapter, `--project-after 50`; stop at the 50 if the projection exceeds the cap.
- Rows: untrained (E12), rank 16, rank 64, next to `gemini-3.5-flash-lite` (T6). Columns, splits, the 430-case
  rows, the account-rule reference row and the list of scam cases called ordinary exactly as in the E12 brief.
  Paired against the untrained model and against flash-lite (2x2 table, McNemar, paired bootstrap interval) for
  correct scenario and for scam called ordinary.
- Rule, declared now: the fine-tuned model is "as good as the closed model" if on the 475 cases it is no more than
  5 points behind flash-lite on correct scenario (88.2%), calls no more scams ordinary (18/225), and flags no more
  than 14/250 ordinary transfers (flash-lite 2/250 plus 5 points). It decides nothing about the live build by
  itself: Minh decides.
- Limits to state in the report: stories, teacher and simulated users are all LLM-written; the teacher asks about
  1.2 questions per session where flash-lite asks 0.36, so the student is expected to ask more; the 45 cases
  rewritten in T6 Part A2 are easy by construction.

## Deliverables

- `experiments/E13/report.md` (English), real spend at the top; sessions per adapter in `experiments/E13/`.
- Adapters kept on the server (not in git); report their path and size, `du -sh .cache/hf`, `df -h`.
- A short E13 section in `EXPERIMENTS.md` and a row in its overview table. Commit and push.
- One line to the planner tab: at the timing gate, after Part B, after Part C, and at once when anything stops a
  part.
