# T6 - Test set v2 (written by GPT) and the first baseline

From: planner tab `Momo_TechContest`. For: `code` tab. Written 2026-11-26.
Minh approved this step on 2026-11-26. **Start only after T4 is finished and the planner tab sends "T6 go".**

Background: `docs/specs/2026-11-26-data-plan-v2.md` (sections 2, 3.7 and 4).

## Goal

A new test set on the 25-scenario catalogue that no training-side model family has touched: tables drawn by code,
wording by GPT. From here on every chat number is measured on it. The 300 cases in `sim/cases/` stay as the v1
record.

## Change of 2026-11-26: T4b comes first

`docs/tasks/T4b-coherent-stories.md` changes `sample_table` (listed values only) and adds the purpose line `viec`
to `make_case`, `OPENING_PROMPT` and `VICTIM_PROMPT`. Test set v2 is built with that generator and those prompts;
"`OPENING_PROMPT` unchanged" below means unchanged from T4b. The check for identical openings runs against
`data/E6/cases_v2.jsonl` as well.

## Part A - Cases

- 475 cases in `sim/cases_v2/`: 15 per scam scenario (225), 25 per ordinary scenario (250). Same keys as the v1
  cases.
- Tables: `sim.cases.make_case` as left by T4 (account label by group, redraw rule for ordinary tables), seed
  `20261128`, a seed used nowhere else. Personas in rotation as in v1.
- **Purpose lines written by GPT, not the train lines.** T4b showed that all stories of `data/E6/cases_v2.jsonl`
  share 78 purpose lines (`sim/viec_dang_lam.yaml`) and that a classifier learns them (C0 v3: 99% on its own val,
  60% on the older val). The test set must not reuse them. Per scenario, one `openai:gpt-6.2-sol` call writes as
  many purpose lines as the scenario has cases (15 or 25, plus 10 spare for replacements), given the scenario's
  `ten`, `mo_ta`, `cac_buoc` and the train lines as "do not reuse or paraphrase these; cover other concrete
  situations of the same kind". Same form as the train lines: what the user believes the transfer is for, in the
  user's words, no scenario name, no "lừa đảo". Each case gets a different line as its `viec`. Save them in
  `sim/cases_v2/_viec.json`; reject a line that equals a train line after lower-casing and stripping, and report
  the number rejected. The report prints all lines of five scenarios (seeded draw) for the planner to read.
- Opening message: `openai:gpt-6.2-sol` with `OPENING_PROMPT` unchanged.
- Order: round-robin over the 25 scenarios, so a stop at the cap leaves a balanced set.
- Re-read, ordinary cases only: `openai:gpt-6.2-sol` gets the opening message and the catalogue lines of the 15
  scam scenarios and answers in JSON whether the message describes one of them (`mau_thuan`, `kich_ban`,
  `ly_do`). A flagged case is dropped and replaced by the next index of the same scenario, at most two rounds.
  - Report every dropped case with its text and the reason.
  - If more than 20% of one scenario's cases are dropped, stop and tell the planner tab: the scenario table is
    the problem, not the cases.
  - Scam cases are never filtered.
- Check that no opening is identical to any opening in `data/E6/cases.jsonl` or `sim/cases/`.
- Nobody trains on `sim/cases_v2/`. The `sonnet` tab must not read it.

## Part B - Runner

- `sim/e5.py`: a flag for the case directory and a seeded stratified order (round-robin over scenarios, seed
  flag). Results of this task go to `experiments/T6/`, never into `experiments/E5/`.
- Protocol unchanged: `tu_do` prompt, at most 3 questions, simulated user `gemini-3.5-flash-lite`.

## Part C - Baseline

- `gemini-3.5-flash-lite` on the 475 cases, one run.
- The same sessions with C0 v2 (T4) and with C0 v3 (T4b) as second opinion, scored as in the v1 report; and both
  classifiers alone on the 475 openings. The planner picks the classifier from these rows.

## Part D - Image trial (lowest priority; skip if A to C are not finished by the evening of 28/11)

- 5 chat screenshots with `gpt-image-2.6-sunburst`, same recipe and `intended` files as `data/E1b/gen`, into
  `data/E1b/gen_gpt/`. Stop after 5 and tell the planner tab; the `sonnet` tab will read them against the
  intended strings before any larger batch.

## Spend

- OpenAI: Part A cap **1.5 USD** (planner's estimate 0.8 USD plus the re-read), Part D cap **0.5 USD**.
- Gemini: Part C cap **1.0 USD** (0.0015 USD per session measured on v1).
- `--project-after 50` on Part C (2 per scenario). If a projection exceeds its cap, stop there and report.
- Never raise a cap yourself.

## Report

`experiments/T6/report.md` (English), real spend per provider at the top, then:

- cases written and dropped per scenario; ten cases printed in full, seeded draw, five ordinary and five scam;
- flash-lite on v2: correct scenario after 0 to 3 questions; scam called ordinary (k/225); ordinary flagged as
  scam (k/250); `chua_du_can_cu`; questions asked; seconds per call; USD per session; every rate as k/n with a
  95% Wilson interval; the same split by account label;
- the same rows with C0 v2 behind it;
- per scenario: correct (k/n), with the new scenarios marked;
- the v1 figures next to them, with the sentence that the two sets are not comparable.

## Deliverables

- Code, `sim/cases_v2/`, report: committed and pushed. A short T6 section in `EXPERIMENTS.md`.
- One line to the planner tab after Part A, after Part C, and at once when a cap or the 20% rule stops a part.
