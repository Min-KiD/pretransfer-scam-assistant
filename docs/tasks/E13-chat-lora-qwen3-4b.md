# E13 - LoRA fine-tune of `Qwen3-4B-Instruct-2507` as the chat model

From: planner tab `Momo_TechContest`. For: `code` tab. Written 2026-11-26.

**Status: not a go yet.** The budgets below are the planner's proposal and are not approved by Minh. Do not start until the planner tab sends "E13 go" with the approved caps. E12 (untrained baseline of the same model) runs first and is the "before" row of this experiment.

## Question

Minh decided on 2026-11-26 to fine-tune one open chat model only: `Qwen/Qwen3-4B-Instruct-2507` (no Gemma for now). Does a LoRA adapter trained on teacher dialogues bring it to the level of `gemini-3.5-flash-lite` (81.3% correct scenario, 10 of 220 scams called ordinary) on the 300 test sessions?

Method fixed by Minh: LoRA only. The base weights stay frozen; only the adapter matrices are trained. No full fine-tune, no unfreezing of layers.

## Part A - Teacher dialogues (API cost)

- Stories: the 3000 `train` stories of `data/E6/cases.jsonl` (200 per scenario; none of their opening messages is in the 300 test cases, checked 2026-11-26). The 300 `val` stories are the validation set. **Never use `sim/cases/` for training or validation.**
- E6 stories have no `tai_khoan` field. Build the account line from `bang_that.nhan_tai_khoan` the same way the test cases do; check on 5 stories by eye and say in the report what was done.
- Teacher: `anthropic:claude-haiku-5-5` as the assistant, same `tu_do` prompt, same JSON schema, simulated user `gemini-3.5-flash-lite`. Reason: on the 300 test sessions it asks 1.30 questions and calls 4 of 220 scams ordinary; `gemini-3.5-flash-lite` asks 0.65 and misses 10.
- Run 1500 train stories (100 per scenario) and 150 val stories (10 per scenario). Keep only sessions whose final `du_doan` equals the story's scenario. Report how many are kept per scenario; if a scenario keeps fewer than 60, say so and do not top up without asking.
- **Order:** seeded stratified (seed `20261126`, round-robin over the 15 scenarios), so that a stop at any point leaves a balanced set.
- Caps (proposal): Anthropic 2.8 USD, Gemini 0.7 USD for this part. Planner's estimate from E10 part C: 0.0015 USD Anthropic and 0.0004 USD Gemini per session. `--project-after 60` (4 per scenario); if the projection exceeds a cap, lower the number of stories per scenario to fit and report; do not raise a cap.
- One training example per assistant turn: the exact prompt of that turn (catalogue, account line, history so far, question count, instruction) as the user message, the teacher's JSON as the assistant message. Use the model's own chat template.

## Part B - Training

- LoRA on the full-precision base (bf16 weights, not quantised: Minh, 2026-11-26), the same setup as `e1/lora_train.py` (plain `peft`, gradient checkpointing; that run peaked at 11.4 GiB on a 4B model). Adapters on all attention and MLP projections (`q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj`). Training and serving then use the same weights.
- Fixed: learning rate 2e-4, linear schedule, warmup 5% of steps, effective batch 16, dropout 0, weight decay 0.01, alpha = rank, loss on the assistant message only, seed 3407, 3 epochs with a checkpoint after each. Set the maximum length from the measured longest training example; report it.
- Two runs only: rank 16 and rank 64.
- Pick one checkpoint per rank by validation loss on the kept val sessions. Report train and validation loss per epoch.
- Where: the company server first (16 GB card; `nvidia-smi` before, never kill another job). Prompts are about 2000 tokens per turn; start with batch 1 x 16 accumulation. If it runs out of memory at rank 64, or the card is busy, stop and tell the planner tab: do not switch to a 4-bit base and do not rent a GPU without asking. Reuse the existing environment (`peft` 0.22 is installed); install nothing new into it.
- Report: trainable parameters, peak VRAM, minutes per epoch, adapter size.

## Part C - Evaluation

- Serve the full-precision base with each chosen adapter through vLLM. Same protocol as E12: the 300 test cases, `tu_do` prompt unchanged, simulated user `gemini-3.5-flash-lite`, greedy, JSON schema enforced, the seeded stratified order added in E12, one run per adapter.
- Cap (proposal): Gemini 0.25 USD per adapter, 0.5 USD in total.
- Rows: untrained (E12), rank 16, rank 64, next to `gemini-3.5-flash-lite`, `claude-haiku-5-5` (the teacher) and `gemma-4-e4b-qat`. Columns and pairing as in E12: scam called ordinary (k/220), ordinary flagged as scam (k/80), correct scenario after 0-3 questions, `chua_du_can_cu`, questions asked, malformed turns, seconds per turn; every rate with a 95% Wilson interval; paired against the untrained model and against `gemini-3.5-flash-lite` (2x2 table, McNemar, paired bootstrap); the E6 second opinion (C0) rows; the scam cases still called ordinary.
- Rule, declared now: the fine-tuned model is "as good as the closed model" if it is no more than 5 points behind `gemini-3.5-flash-lite` on correct scenario (81.3%), calls no more scams ordinary than it does (10 of 220), and flags ordinary transfers no more than 5 points more often (7 of 80). It decides nothing about the live build by itself: Minh decides.
- Known limit to state in the report: teacher, training stories and simulated user are all LLM-written; the test sessions come from the same generator as the training stories.

## Deliverables

- `experiments/E13/report.md` (English), real spend per provider at the top.
- Teacher dialogues under `data/E13/` (kept and dropped, with the reason), adapters kept on the server, not in git.
- A short E13 section in `EXPERIMENTS.md` and a row in its overview table. Commit and push.
- One line to the planner tab after each part, and at once when a projection rule or a cap stops a part.
