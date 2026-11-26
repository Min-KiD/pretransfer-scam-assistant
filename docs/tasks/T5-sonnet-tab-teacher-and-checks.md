# T5 - Sonnet 5.5 tab: scenario review, teacher dialogues, checks

From: planner tab `Momo_TechContest` (herdr pane `wG:p4`). For: the `sonnet` tab (omp running
`claude-sonnet-5-5` on Minh's subscription). Written 2026-11-26.
Minh approved this tab and its work on 2026-11-26. Parts 1 and 2 are a go now. Parts 3 and 4 each wait for one
line from the planner tab.

Repo: `/home/minhnv/Documents/CV/momo-techcontest/pretransfer-scam-assistant`. Work there.
Background: `docs/specs/2026-11-26-data-plan-v2.md`, `README.md`.

## What the project is, in five lines

- A pre-transfer assistant for an e-wallet: before the user sends money it asks at most 3 questions and says
  which known scenario the situation looks like (scam or ordinary). It warns; it never blocks.
- The scenario catalogue is `scenarios/*.yaml` (15 today, 25 after task T4, which the `code` tab is doing now).
- The chat protocol is `sim/run.py::run_tu_do`: one prompt per turn (`FREE_PROMPT`), JSON answer
  `{du_doan, cau_hoi}`, at most 3 questions, a simulated user answers from a hidden story table.
- We want to fine-tune a small open model (Qwen3-4B) on dialogues in which a strong model plays the assistant.
  You are that strong model: the teacher.
- The test set will be written by GPT. Your family must take no part in it.

## Change of 2026-11-26 (after T4): stories come from `data/E6/cases_v2.jsonl`

The T4 stories turned out incoherent (off-scenario values in 35-55% of rows; most loan-scam stories never mention
a loan). Brief `docs/tasks/T4b-coherent-stories.md` regenerates all stories into `data/E6/cases_v2.jsonl`. Wherever
Parts 3 and 4 below say `data/E6/cases.jsonl`, read `data/E6/cases_v2.jsonl`; no row filter is needed for ordinary
scenarios any more. Stories you write yourself in Part 4 use `make_case` and `OPENING_PROMPT` as left by T4b (they
carry the purpose line `viec`). "T5 trial go" comes after T4b is finished.

## Rules

- **No Claude API.** Every Claude call goes through this tab's subscription: the `completion(prompt, schema=...)`
  helper of the omp eval kernel. Never read or use `CLAUDE_API_KEY`. Never print values from `.env`.
- Before any run, check which model `completion()` resolves to. If it is not `claude-sonnet-5-5`, stop and tell
  the planner tab.
- If the subscription rate-limits you, slow down and report the sustained rate. Do not switch provider.
- Gemini (`gemini-3.5-flash-lite`, the simulated user) costs money: cap **1.0 USD** for this whole brief, counted
  with `core.llm.USAGE`. Never raise a cap yourself.
- Never read `sim/cases/` (the 300 test cases) and never read anything under a future `data/test_v2/`.
  Never use `data/E1b/real` for anything but looking.
- The `code` tab edits `core/`, `sim/`, `e6/`, `scenarios/` and `tests/` in this same working tree right now.
  Write only under `teacher/` (new), `data/T5/` and `experiments/T5/`. Edit nothing else. If an import breaks
  because of a half-finished edit, wait and retry.
- Commit only your own paths with the eval `commit` helper (`d = await commit.draft(repo=..., silent=True)`,
  `await d.only(...)`, `await d.commit(subject, [bullets])`), then `git push origin master`. `data/` is not in git.
- Repo code runs with `.venv/bin/python`. The eval kernel is a different Python: if repo imports fail there, call
  small `.venv/bin/python` helpers through `sh()`.
- Every `.md` you write is in English. Reports go to the planner tab as one line:
  `herdr pane run wG:p4 "[sonnet tab] <text>"`. Do not poll and do not message Minh.

## Part 1 - Review the 10 new scenario files (go now, do this first)

Files: `docs/specs/scenarios-v2/*.yaml` (the `code` tab may already have moved them to `scenarios/`; read
whichever exists). The planner wrote them; the 6 ordinary ones have no external source. They are about to be
frozen, and stories will be generated from them.

For each file, as an independent reader who knows how people in Vietnam actually pay and get scammed:

- Is `mo_ta` accurate and natural Vietnamese? Would a model reading only `id: ten - mo_ta` tell this scenario from
  its neighbours, in particular from the one named in `doi_chieu_voi` and from the scenarios listed in section 3.4
  of the spec (`mo_vi_tra_sau_nhan_hoa_hong` against `ctv_online`, `bt_dat_dich_vu_co_xac_nhan` against
  `bt_mua_online_nguoi_ban_moi`, `bt_mung_cuoi_gop_quy` against `bt_chuyen_cho_nguoi_than`)?
- Are the probabilities in `truong` plausible? Name any that look wrong and say what you would put.
- Does any ordinary scenario describe something that is often a scam in practice, or leave out the most common
  ordinary form of that payment?
- For the 4 scam files: open the URLs marked `da_doc` and check that `mo_ta` and `cac_buoc` say nothing the pages
  do not support.

Deliverable: `experiments/T5/scenario-review.md`, problems first, each with the file, the line and a proposed
replacement. Do not edit the scenario files. One line to the planner tab when done. Keep this under an hour.

## Part 2 - Teacher runner (go now, after Part 1)

Build `teacher/run.py` (or a notebook-style script the eval kernel can drive): the loop of
`sim/run.py::run_tu_do` with the assistant call replaced by `completion()`.

- Reuse `FREE_PROMPT`, `free_schema`, `account_line`, `history_text` and `victim_reply` from `sim/run.py` by
  import. Do not copy the prompt text: the student must be trained on the exact prompt the evaluation uses.
- Save, per session: story id, scenario, group, the account line, and for every assistant turn the exact prompt
  string and the JSON you returned; the simulated user's replies; seconds per call.
- Resumable: a session already saved is skipped.
- Smoke test on 5 `train` rows of `data/E6/cases.jsonl` (5 different scenarios). E6 rows have no `tai_khoan`:
  build it from `bang_that` (`loai_tai_khoan`, `ten_khop_tu_xung`) and draw `nhan_tai_khoan` with the generator
  rule of T4 (ordinary: `moi` 0.9, `dang_bi_bao_cao` 0.1; scam: `moi` 0.6, `dang_bi_bao_cao` 0.25,
  `da_xac_nhan` 0.15), seeded per story id.
- Report to the planner tab: it works or not, seconds per call, which Python ran what.

## Part 3 - Trial (wait for "T5 trial go"; it comes after T4 is finished)

- 75 stories: 3 per scenario of the 25, `train` rows of `data/E6/cases.jsonl`, seeded draw (seed `20261126`),
  round-robin over scenarios. For ordinary scenarios use only rows that pass the T4 rule (the function the `code`
  tab adds to `sim/cases.py`).
- Simulated user: `gemini-3.5-flash-lite` through `victim_reply`, unchanged.
- Report (`experiments/T5/trial.md`): correct scenario (k/75); scam called ordinary (k/45); ordinary called scam
  (k/30); `chua_du_can_cu`; questions per session; seconds per call; sustained calls per minute and any rate
  limit met; projected hours for Part 4; Gemini spend. Every rate as k/n with a 95% Wilson interval.
- Sonnet 5.5 has never been measured in this role. If it is clearly worse than the 300-session figures of
  `gemini-3.5-flash-lite` (81.3% correct scenario) and `claude-haiku-5-5` (81.7%), say so plainly: the planner will
  then reconsider the teacher.
- Ten sessions printed in full in the report, picked by a seeded draw, for the planner to read.

## Part 4 - Teacher dialogues (wait for "T5 full go")

Target: 60 sessions per scam scenario and 90 per ordinary scenario for training (900 + 900), plus 10 per scenario
for validation (250).

- Half of each scenario's sessions start from flash-lite stories (`data/E6/cases.jsonl`, `train` rows for
  training, `val` rows for validation; the simulated user is `gemini-3.5-flash-lite`).
- **Your own purpose lines for your half.** The flash-lite stories share 78 purpose lines
  (`sim/viec_dang_lam.yaml`), which is narrow. Before writing stories, write 20 purpose lines per scenario through
  `completion()` (given `ten`, `mo_ta`, `cac_buoc` and the existing lines as "do not reuse or paraphrase"; same
  form: what the user believes the transfer is for, in the user's words, no scenario name, no "lừa đảo"). Save them
  as `data/T5/viec_sonnet.json` and use them, in rotation, as `viec` of the cases you draw. Never read
  `sim/cases_v2/` (it will hold GPT's lines for the test set).
- The other half start from stories you write: draw fresh tables with `sim.cases.make_case` (seed `20261127`,
  never a seed used elsewhere), write the opening with `OPENING_PROMPT` through `completion()`, and play the
  simulated user with `VICTIM_PROMPT` through `completion()` in a separate call that sees only what
  `victim_reply` would send. Mark these sessions `user_family: claude`.
- Order: seeded, round-robin over the 25 scenarios, so a stop at any point leaves a balanced set.
- Keep a session only if its final `du_doan` equals the story's scenario. For `bt_mua_online_nguoi_ban_moi`
  also keep `chua_du_can_cu`. Save dropped sessions with the reason. If a scenario keeps fewer than two thirds of
  its target, say so; do not top up without asking.
- Output: `data/T5/sessions.jsonl` (everything), `data/T5/train.jsonl` and `data/T5/val.jsonl` (one row per
  assistant turn: `{"messages": [{"role": "user", "content": <exact prompt>}, {"role": "assistant", "content":
  <the JSON, compact, keys in the order du_doan, cau_hoi>}], "story_id", "scenario", "turn"}`).
- Report (`experiments/T5/report.md`): kept and dropped per scenario; the same rates as the trial on all sessions
  before filtering; longest prompt in tokens (Qwen3 tokenizer if available locally, else characters); hours taken;
  Gemini spend.

## Part 5 - The teacher on test set v2 (added 2026-11-26, go on the planner's message)

Minh's question: was the teacher measured before the student learns from it? It was measured on train-type stories
only (Part 4: 1,895/2,050 correct, 0/1,050 scams called ordinary), never on the same cases as
`gemini-3.5-flash-lite` (T6: 419/475, 18/225, 2/250). This part gives the teacher's row on test set v2.

- **The rule "never read `sim/cases_v2/`" is lifted for this part only**, because `data/T5/` is finished and
  frozen. From now on this tab writes no training story, purpose line or teacher dialogue for any model; if the
  planner ever asks for more training data, remind it of this line.
- Run the teacher (`teacher/run.py`, same prompts, at most 3 questions) on the 475 cases of `sim/cases_v2/`
  (`<scenario>__<i>.json`; skip `_*.json` and `_replaced/`), in the order `sim.e5` gives with `--order-seed
  20261128`; simulated user `gemini-3.5-flash-lite` through `victim_reply` (`VICTIM_PROMPT_VIEC`). One run, no rerun
  to pick a number. Gemini cap for this part: 0.3 USD (expected about 0.2); stop and report at the cap.
- Output `data/T5/test_v2_sessions.jsonl` and `experiments/T5/test_v2.md` with, next to the flash-lite row computed
  from `experiments/T6/sessions.jsonl` (same cases, pair them by case id):
  - correct scenario after 0, 1, 2, 3 questions; scam called ordinary (k/225); ordinary flagged as scam (k/250);
    `chua_du_can_cu` (k/475, split scam / ordinary); questions per session; all k/n with 95% Wilson intervals;
  - the same rows split by group and by account label, and on the 430 cases outside `chuyen_nham_tien`,
    `gia_don_hang_lon_mua_ho`, `mo_vi_tra_sau_nhan_hoa_hong` (those 45 were rewritten and are easy);
  - paired against flash-lite: 2x2 right/wrong table and McNemar for correct scenario and for scam called ordinary;
  - of flash-lite's 18 scams called ordinary: what the teacher answered on each (case id, answer, questions);
  - every scam the teacher called ordinary or `chua_du_can_cu`, with the full dialogue;
  - does asking help: sessions wrong at turn 0 and right at the end, and the reverse.
- One line to the planner when done.

## Part 6 - Opus 5.5 as a teacher candidate, on test set v2 (added 2026-11-27, Minh's request)

Minh wants the best available teacher. Part 5 gave Sonnet 5.5: correct 410/475, scam called ordinary 0/225,
ordinary flagged 9/250, `chua_du_can_cu` 40/475 (36 ordinary). Is Opus 5.5 clearly better on the same 475 cases?

- Model: Claude Opus 5.5 **on the subscription**, through `completion()`: find which tier or pinned model
  (`model="slow"` or `m<N>`, see `cfg://modelRoles`) is Opus 5.5 and pass it; do not change settings and do not use
  an API key. If no tier maps to Opus 5.5, stop and tell the planner. Write the model id returned by the calls
  into the report.
- Only the assistant changes. Prompts, cases, order (`--order-seed 20261128`), simulated user
  (`gemini-3.5-flash-lite`, `VICTIM_PROMPT_VIEC`), at most 3 questions: identical to Part 5. One run, no rerun.
- Pilot first: the first 50 sessions of the seeded order (2 per scenario). Send the planner one line (seconds per
  call, calls per minute, any rate limit or quota message) and go on without waiting unless a limit was hit.
  Gemini cap 0.3 USD.
- Report `experiments/T5/test_v2_opus.md` (sessions `data/T5/test_v2_opus_sessions.jsonl`): the Part 5 tables with
  three columns (Opus, Sonnet, flash-lite), paired Opus vs Sonnet (2x2 table, McNemar) for correct scenario, for
  correct on the 250 ordinary cases, and for scam called ordinary; `bt_tra_shipper_khi_nhan_hang` and
  `bt_mua_online_nguoi_ban_moi` shown apart; every scam Opus called ordinary or `chua_du_can_cu` with the dialogue.
- Rule, declared now: Opus replaces Sonnet as teacher only if it calls at most 1 of 225 scams ordinary **and** is
  better than Sonnet on correct scenario (all 475, or the 250 ordinary) with paired p < 0.05. Otherwise Sonnet's
  data stands. If Opus wins, the planner will ask for the teacher turns to be regenerated on the **same** 2,050
  stories and openings of `data/T5/sessions.jsonl` (no new story or purpose line, so the test set this tab has
  read cannot leak): not a go yet.

## Later jobs for this tab (not a go, listed so you know)

- Reading generated test images against the strings they were asked to contain.
- Reading samples of generated stories for the planner.
