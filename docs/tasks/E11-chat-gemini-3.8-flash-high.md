# E11 - Chat with `gemini-3.8-flash` at high thinking

From: planner tab `Momo_TechContest`. For: `code` tab. Issued 2026-11-25. Minh asked for this run on 2026-11-25 ("giao cho tab code đi"): this brief is a go.

## Question

Minh ranks "few scams called ordinary" above "few ordinary transfers flagged". On the 75 `v1` cases, `gemini-3.8-flash@low` missed 1 of 55 scams against 6 of 55 for `gemini-3.5-flash-lite` at its default level, but its 42 output tokens per call show that it hardly thinks at `low`. What does `high` buy, and what does it cost in seconds and USD?

## Run

- Model `gemini-3.8-flash@high`, chat only, same protocol as E5: `tu_do` prompt unchanged, simulated user `gemini-3.5-flash-lite`, one run, no reruns to pick a number.
- Cases: the 75 `v1` cases (the set every closed model in E5 ran on). Not the 300.
- `--cap-usd 1.8` for the whole run (assistant + simulated user), `--project-after 30`.
  - Planner's estimate: 1,000-3,000 thinking tokens per call, 0.010-0.026 USD per session, so 0.8-2.0 USD for 75 sessions.
  - If the projection after 30 sessions exceeds the cap: **stop at those 30 sessions** and report them. Do not continue to the cap.
- Gemini cap scope (E4 + E5 + E6 + E10 + this run): 22.71 of 25 USD spent before this run. Never raise a cap yourself.
- No server, no GPU, no other model, no prompt change.

## Report

Same columns as the E5 table, for `gemini-3.8-flash@high` next to the existing rows on the same 75 cases (`gemini-3.5-flash-lite` default and `@medium`, `gemini-3.8-flash@low`, `gemini-4-carbon`, `gpt-6.2-sol`, `claude-haiku-5-5`, `gemma-4-e4b-qat`):

- correct scenario after 0-3 questions; scam called ordinary (k/55); ordinary flagged as scam (k/20); `chua_du_can_cu`; questions asked; every rate as `k/n` with a 95% Wilson interval;
- thinking tokens per call (median, p90); seconds per call split into "asks a question" and "concludes" (mean, p90); model seconds per session (mean, p90); USD per session;
- paired against `gemini-3.8-flash@low` and against `gemini-3.5-flash-lite` default on the same cases: 2x2 right/wrong table, McNemar, paired bootstrap interval; the same pairing for "scam called ordinary" on the 55 scam cases;
- the list of scam cases each of the three still calls ordinary (case id, scenario).

No rule is declared in advance: on 75 cases the interval is about +-10 points, so this run describes cost and direction and decides nothing by itself. Say so in the report.

## Deliverables

- `experiments/E11/report.md` (English), real spend at the top.
- A short E11 section in `EXPERIMENTS.md` and a row in its overview table. Commit and push.
- One line to the planner tab when done, or when stopped by the projection rule.
