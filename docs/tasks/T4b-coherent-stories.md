# T4b - Coherent stories: sample listed values only, state what the transfer is for

From: planner tab `Momo_TechContest`. For: `code` tab. Written 2026-11-26. **This brief is a go** (same kind of work
as T4, inside the spend Minh approved on 2026-11-26). It comes before T6: do not start T6.

## Why (measured by the planner on `data/E6/cases.jsonl` after T4)

1. **The generator samples from the smoothed distribution.** `sim.cases.sample_table` uses
   `core.infer.single_dist`, which gives every unlisted value at least `FLOOR = 0.02`. With 16 values each in
   `tu_xung` and `ly_do_tien` this adds up: `bt_tra_shipper_khi_nhan_hang` lists `tu_xung: shipper 0.98` and gets 169 of
   220; `tinh_cam_qua_mang_gui_qua` gets "khách đặt hàng", "nhà tuyển dụng", `ly_do_tien: tra_no`. Per scenario only
   97 to 144 of 220 stories have listed values in the four fields `tu_xung`, `ly_do_tien`, `nguoi_lien_lac`, `kenh`,
   and 15 to 100 of 220 in all single-choice fields.
2. **The story never says what the transfer is for when no enum value carries it.** Share of stories (opening
   plus three answers) that contain a word of the scenario's subject: `vay_online_dong_phi_truoc` 23 of 220
   ("vay", "giải ngân"); `tinh_cam_qua_mang_gui_qua` 43 of 220 ("quà", "hải quan", "sân bay", "nước ngoài");
   `bt_dat_dich_vu_co_xac_nhan` 29 of 220; `mo_vi_tra_sau_nhan_hoa_hong` 100 of 220. Such a story cannot be told
   from `gia_ngan_hang` or a generic purchase by anyone. This explains C0 v2's 40% on the loan scenario and, likely,
   real loan-scam narratives going to `bt_tra_no_khoan_vay` (the only training stories that say "vay").

A real user asked "Bạn đang chuyển khoản này vì việc gì?" says what the transfer is for. The stories must too.

## Change

1. `sim/cases.py::sample_table`: draw only values the scenario lists.
   - Single-choice field: listed values, probabilities renormalised to 1. A field the scenario does not list keeps
     today's behaviour.
   - Multi-choice field: only listed values can appear, each with its listed probability.
   - `core/infer.py` is not touched (smoothing stays for inference).
   - The redraw rule for ordinary tables stays.
2. Purpose line. `sim/viec_dang_lam.yaml` (written by the planner, committed with this brief) has 3 or 4 lines
   per scenario: what the user believes the transfer is for.
   - `make_case` draws one with the case's rng and stores it in the case as `viec`.
   - `OPENING_PROMPT` and `VICTIM_PROMPT` get it as the first line of the story block ("Việc bạn đang làm: ...").
     The opening must say this purpose in the user's own words (the persona may shorten it, not drop it); the
     other details stay "1-3 details, not everything". Keep every other rule of both prompts.
   - A case without `viec` (v1 cases, old rows) must still run: `sim/cases/` and v1 results are not regenerated.
   - A test fails if a scenario has no entry in the file.
   - You may fix wording in `sim/viec_dang_lam.yaml` if a line breaks a prompt; tell the planner which.
3. `FREE_PROMPT`, `free_schema`, the catalogue line and `scenarios/` are **not** changed.

## Pilot, then a gate

- 10 stories per scenario (250), seeded, new output file `data/E6/cases_v2.jsonl` (the 5,500 old rows stay as the
  v1-generator record; nothing reads them for v2 work from now on).
- Send the planner one line with: spend; per scenario the share of openings that carry the purpose; where to read
  3 full stories per scenario (a file under `experiments/T4b/`). Then **wait for "T4b full go"**.

## Planner's decisions after the pilot (2026-11-26) - "T4b full go" with these changes

- Your prompt fix (rephrase the purpose, write with diacritics) is accepted.
- **Values in plain words.** In pilot B, 14 of the 17 simulated users with `tu_xung: nguoi_ban` who were asked "Họ tự
  giới thiệu là ai?" answered "bạn bè" or "người quen": the raw id reads as "người bạn". `sim/gia_tri_bang_loi.yaml`
  (planner, committed) maps every value of the ten story fields to plain Vietnamese. `story_text` uses it for cases
  that carry `viec`; cases without `viec` (v1) keep the old text byte for byte. `khac` stays as it is. A test fails
  if a value of those fields has no entry.
- The 250 pilot B rows are discarded (keep them under `.cache/logs/t4b/`); the full run starts from case 0.
- Sizes: 190 train + 20 val per scenario (5,250). Cap for this brief raised by the planner to **2.75 USD**
  (0.228 spent, about 2.3 projected for the run).
- Automatic stop: after the first 500 stories, among cases with `tu_xung: nguoi_ban` whose questions include "Họ tự
  giới thiệu là ai?", fewer than 10% of the answers may contain "bạn bè", "người bạn" or "người quen". If not, stop
  and tell the planner. The report gives this figure for the whole file.

## Full run (after the go)

- 220 per scenario for all 25 (200 train, 20 val), interleaved over scenarios, resumable, into
  `data/E6/cases_v2.jsonl`. `gemini-3.5-flash-lite`. Cap **2.5 USD** for this brief, pilot included (planner's
  estimate 2.4 USD from T4's 0.93 USD per 2,200). If the projection after the pilot is above the cap, say so in
  the pilot line and propose a smaller train size; never raise the cap yourself.
- C0 retrained on the new file (call it C0 v3; keep v1 and v2 weights and predictions).

## Report

`experiments/T4b/report.md` (English), real spend at the top:

- per scenario: share of stories with all listed values (must be 100%), share of openings carrying the purpose;
- C0 v3 on val: correct scenario, scam called ordinary, ordinary called scam (k/n, Wilson 95%), per scenario, next
  to C0 v2's row (different val sets: say so);
- the 84 labelled real narratives: correct scenario, called ordinary; **every narrative called ordinary listed with
  its id, label, answer and a one-line summary**, for v2 and v3;
- five stories per scenario, seeded draw.

## Deliverables

Code, tests, report, a short T4b section in `EXPERIMENTS.md`; README Data section updated to 25 scenarios and the
new story file. Committed and pushed. One line to the planner at the pilot gate and at the end:
`herdr pane run wG:p4 "[code tab] <one line>"`.
