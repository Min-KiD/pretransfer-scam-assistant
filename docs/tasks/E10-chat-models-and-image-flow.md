# E10 - Pick the models: larger open chat models, thinking level, Haiku 5.5, and the full flow with an image (merged vs split)

From: planner tab `Momo_TechContest`. For: `code` tab. Issued 2026-11-23, revised the same day. Minh approved parts A-D on 2026-11-23.
Follows E4 and E5 (`experiments/E4/report.md`, `experiments/E5/report.md`). E7-E9 are reserved for other work, so this batch is E10.

**Status (2026-11-23 evening): PREPARE ONLY.** Minh approved the batch and the new Gemini cap, but wants the runs started when he is back.
Allowed now: download the three part-A models to the server, write the E10 code and scripts, build the part-D case list. Not allowed until the planner tab says go: any paid API call, any experiment run (including serving a model for E5 or E4).

## Questions

1. Does an open chat model larger than 4B, still fitting the 16 GB card, get within 5 points of `gemini-3.5-flash-lite`?
2. Does turning thinking up on `gemini-3.5-flash-lite` stop it concluding too early (10 of 220 scams called ordinary), and at what price and latency?
3. Where does Claude Haiku 5.5 stand against Gemini, for chat and for reading screenshots?
4. When a session has a screenshot: is letting the chat model look at the image itself ("merged") different from reading the image to JSON first and chatting on the JSON ("split")?

Already decided, not to be re-proved: the assistant asks its own questions (`tu_do`), at most 3; the app keeps the split flow unless part D shows merged is clearly better (rule in part D).

## Money and order

- Before any API call: add up the real Gemini spend so far from every `cost.json`, `calls.jsonl` and report cost table, and put it at the top of `experiments/E10/report.md`. Planner's sum from the E4, E5 and E6 reports is about 18.2 USD.
- **Gemini cap is now 25 USD in total** (Minh, 2026-11-23; was 20). Planner's estimate for this batch: part A 0.6, part B 1.0, part D 2.7 USD.
- **Part A runs first** (its only API cost is the simulated user, about 0.2 USD per model). Downloads are the slowest step.
- **Part C runs only with a working Claude key** (see part C).
- Each run has its own `--cap-usd`, given per part. At the cap: stop and report, never raise it yourself.
- Server: one GPU, one model at a time. Never kill other people's jobs. Never restart a download that is in progress.

## Part A - Larger open chat models

Same protocol as E5: 300 cases, the `tu_do` prompt unchanged, simulated user `gemini-3.5-flash-lite`, one run per model.

| Model | Size (Hugging Face, 2026-11-23) | Notes |
|---|---|---|
| `Qwen/Qwen3-14B-AWQ` | 10.0 GB | Text only, official 4-bit build |
| `Qwen/Qwen3-8B-FP8` | 9.4 GB | Text only |
| `google/gemma-4-E4B-it` | 16.0 GB unquantised: does not fit 16 GB | Use Google's own quantised build `google/gemma-4-E4B-it-qat-w4a16-ct` (11.5 GB). If vLLM cannot load it, record the error and report; do not switch to a third-party build |

- Thinking off as in E5 (`enable_thinking: false`), greedy decoding, JSON schema enforced.
- Report as in E5: correct scenario after 0-3 questions, ordinary flagged as scam, scam called ordinary, questions asked, malformed outputs, seconds per turn (mean, p90), peak VRAM, weight size, load time, licence and revision.
- Run the E6 second opinion (C0) on each model's sessions (CPU, free).
- **Gemma 4 is multimodal, so also run it as a screenshot reader** while it is loaded: E4 modes J and Ju, `web` first with one request at a time (that is the latency number), then the other sets. Score with `e1.score_e4`. No API cost.
- Keep the weights on the server until Minh picks (175 GB free on 2026-11-23). Report `du -sh .cache/hf` at the end.
- M2 rule as before: no more than 5 points behind `gemini-3.5-flash-lite` (81.3%, 244/300) on correct scenario, and ordinary-flagged-as-scam no more than 5 points higher.

## Part B - Thinking level of `gemini-3.5-flash-lite`, chat only

- This model's default is `minimal` (close to off); every E2 and E5 number was run there (median 33 output tokens per turn, thinking included).
- Run `gemini-3.5-flash-lite@medium` once on the 300 cases. No `high` run (Minh: higher levels only cost more and run slower).
- Screenshot reading stays at the default level; it is not part of this test.
- Also report: thinking tokens per turn (median, p90), seconds per turn, USD per session.
- `--cap-usd 1.5`. After the first 30 sessions, project the cost of all 300; if it exceeds the cap, stop at the 75 `v1` cases and report.

## Part C - Claude Haiku 5.5

- **Blocked on the key (2026-11-23 18:10).** The key in `.env` is of type `sk-ant-usr`. The API answers "This API key is not scoped to a workspace"; with the only listed workspace id it answers 404 "Workspace not found". Minh has to supply a Console API key (`sk-ant-api03-...`). Make one test call first; if it fails, skip part C and say so in the report.
- Price (Anthropic pricing page, read 2026-11-23): 0.10 / 0.50 USD per 1M tokens in / out for prompts up to 100,000 tokens. Add it to `PRICES`.
- Call the native Anthropic API with the output constrained to the JSON schema. The OpenAI compatibility layer ignores `response_format`, so it is not a fair comparison.
- Chat: 300 cases. Screenshots: E1 method B on `web`, `gen`, `gen_ref`, `E1`, `E1b`, scored with `e1.score_e4`.
- Cap 2 USD for all of part C (this replaces the "`web` and `v1` only" limit of plan section 7, for Haiku only; approved by Minh 2026-11-23).

## Part D - Full flow with an image: merged vs split

### Cases

- 300 cases, 20 per scenario, images taken from `data/E4/val` (13 scenarios) and `data/E4/val_la` (2 scenarios), fixed seed, image list committed.
- Opening message: picked by seed from 5 fixed neutral sentences (like "Mình nhận được tin nhắn này, có nên chuyển không?"), no model call. Purpose: what happened is only in the image.
- The simulated user answers from the image content: its prompt gets the scenario description and the chat messages from the image's ground truth (`messages`). `bang_that` fields the image shows (channel, claimed identity, request...) must match the image. Check 15 cases by eye (one per scenario) before running.
- Receiving-account label: sampled as in `sim/cases.py`.
- Real screenshots have no scenario label, so they cannot be used here. State this limit in the report.

### Arms

| Arm | What the chat model sees | Notes |
|---|---|---|
| `no_image` | Opening message only | Floor: shows what the image adds |
| `split` | The JSON that `core.vision.read_image` reads from the image, inserted into the prompt as data | What the app does today |
| `split` run 2 | Same, rerun from scratch (image reading included) | Measures the run-to-run difference of one configuration |
| `merged` | The image itself, attached at every turn; no JSON | One call per turn |

- Main pair: `gemini-3.5-flash-lite` for both reading and chat, in all four arms. Same model everywhere so that only the wiring changes.
- Second pair, `split` only: reader `gemini-3.5-flash-lite`, chat = the best open model of part A (the "closed reader, open chat" setup).
- If part C runs: Haiku 5.5 in `split` and `merged`.
- The chat prompt is identical across arms except for the image data block. Quote the differing part in the report.

### Measures

- Correct scenario after at most 3 questions; scam called ordinary; ordinary flagged as scam; `chua_du_can_cu`; questions asked.
- Time the user waits for the assistant's first reply (`split` includes the reading step), and total per session.
- Tokens and USD per session.
- `split`: string match rate of the reading step on these 300 images, and the number of wrong conclusions where the reading step had misread.
- Paired comparison on the same cases: 2x2 right/wrong table between two arms, McNemar test, paired bootstrap interval for the difference.

### Rules declared in advance

- Baseline noise = difference in correct scenario between `split` run 1 and run 2.
- `merged` and `split` count as **equal** if the difference in correct scenario is at most 5 points, or the 95% paired interval contains 0.
- The app moves to `merged` only if `merged` beats `split` by more than 5 points, the interval excludes 0, and the difference is larger than the baseline noise. In that case tell Minh; do not change the app yourself.
- One run per arm (except the declared `split` run 2); no reruns to pick a number.

`--cap-usd 3.0` for all of part D.

## Not in this batch

- **No fine-tuning of screenshot-reading models at all.** Minh dropped that direction on 2026-11-23 (LoRA improved accuracy only within noise on real screenshots and does not fix the 8-16 s per image). The LoRA on `qwen3.5-4b` is cancelled.
- Fine-tuning a chat LLM: later, after part A shows which open model is closest.
- The re-ask layer (`docs/specs/2026-11-23-re-ask-layer-proposal.md`): a proposal only.
- Changes to `app/`: wait for the results of this batch.

## Deliverables

- `experiments/E10/report.md`: four parts, every rate as `k/n` with a 95% Wilson interval; real costs; for a part that did not run, the reason.
- `EXPERIMENTS.md`: a short E10 section in the style of the earlier ones.
- Commit and push. No weights, no `experiments/` in git.
- After each part, send the planner tab one line; do not wait for the whole batch.
- Language: docs and reports in English from now on (Minh reads none of them; he talks to the planner tab only).
