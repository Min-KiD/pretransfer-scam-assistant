# T4 - Catalogue v2: 25 scenarios, cleaner case generator, M3 retrained

From: planner tab `Momo_TechContest`. For: `code` tab. Written 2026-11-26.
**Not dispatched.** Needs Minh's explicit go and his approval of extra Gemini budget (see Spend).

Background and evidence: `docs/specs/2026-11-26-data-plan-v2.md` (sections 3 and 3.7).

## Goal

The catalogue grows from 15 to 25 scenarios (15 scam, 10 ordinary). The case generator stops producing ordinary
cases that read like scams. M3 (C0) is retrained on the 25 scenarios. After this task the catalogue is frozen: the
GPT-written test set, the baselines, E12 and the teacher dialogues are all built on it.

Not in this task: test set v2, any chat-model run, E12, E13, teacher dialogues, app flow changes, new images.

## Do not touch

- The 300 files in `sim/cases/` and the existing rows of `data/E6/cases.jsonl` (the v1 record).
- `experiments/E5` to `experiments/E11`, `data/E6/preds/*.jsonl`, the v1 C0 weights in `.cache/e6/c0/`.
  Write v2 weights and predictions to separate paths.
- `data/E1b/real`.

## Changes

### 1. Schema (`core/schema.py`)

- `tu_xung` gains `nguoi_quen_qua_mang`, `khach_dat_hang`, `to_chuc_dich_vu`, `chinh_minh`.
- `ly_do_tien` gains `hoa_don`, `tra_no`, `mung_gop_quy`, `chuyen_noi_bo`, `tien_vay_chuyen_di`.
- No new field: `len(FIELDS)` stays 14.
- Extend the two field labels so every new value is explained in Vietnamese, in the style of the existing notes:
  - `nguoi_quen_qua_mang`: someone known only online, never met;
  - `khach_dat_hang`: someone ordering goods from the user;
  - `to_chuc_dich_vu`: school, hospital, utilities, travel company, training centre;
  - `chinh_minh`: the user's own account;
  - `hoa_don`: tuition, utilities, official fees from a notice;
  - `tra_no`: instalment, card or loan repayment on a loan already received;
  - `mung_gop_quy`: wedding or funeral gift, shared fund;
  - `chuyen_noi_bo`: between the user's own accounts;
  - `tien_vay_chuyen_di`: money just borrowed or advanced, sent on to someone else at their suggestion.
- `core/lookup.py::ORG_ROLES` gains `to_chuc_dich_vu`.

### 2. Scenarios

- Move the 10 files from `docs/specs/scenarios-v2/` into `scenarios/` unchanged. `python -m core.scenarios` must
  report 25 scenarios and no issue.
- The key `doi_chieu_voi` is informational. Do not turn it into `kho_phan_biet_voi`.
- Relabel 9 real narratives (`data/narr/real/`, field `kich_ban`, currently `khac`):

| Narrative | New label |
|---|---|
| `narr_034`, `narr_035`, `narr_036`, `narr_083`, `narr_084` | `tinh_cam_qua_mang_gui_qua` |
| `narr_032` | `vay_online_dong_phi_truoc` |
| `narr_007` | `gia_don_hang_lon_mua_ho` |
| `narr_033`, `narr_040` | `mo_vi_tra_sau_nhan_hoa_hong` |

  `narr_003`, `narr_048`, `narr_063`, `narr_070`, `narr_082` stay `khac`.

### 3. Case generator (`sim/cases.py::make_case`)

Applies to every case generated from now on.

- Account label: draw `nhan_tai_khoan` by group, not evenly.
  - Ordinary: `moi` 0.9, `dang_bi_bao_cao` 0.1.
  - Scam: `moi` 0.6, `dang_bi_bao_cao` 0.25, `da_xac_nhan` 0.15.
  - Keep these as a constant in the generator, not in the scenario files (the computed core must not start
    scoring the label).
- Ordinary scenarios: redraw the table while it carries any of
  - `yeu_cau` containing `cai_app`, `doc_otp` or `nap_them_de_rut`;
  - `ly_do_tien` in `nhiem_vu`, `dau_tu`, `tai_khoan_an_toan`, `khac_phuc_loi`, `hoan_tien`, `tien_vay_chuyen_di`;
  - `duoc_dan_cach_tra_loi` = `co`;
  - `ap_luc` containing `doa` or `giu_bi_mat`.
- Put the rule in one function; the M3 training step below uses the same function.
- Scam scenarios: no redraw.

### 4. Stories for the 10 new scenarios (`sim/e6_data.py`)

- 220 per new scenario (200 train, 20 val), appended to `data/E6/cases.jsonl`. Existing rows are skipped by the
  resume logic; check that before spending.
- Order: interleave the batches across scenarios (batch k of every scenario before batch k+1), so a stop at the
  cap leaves every scenario with the same count. The current order finishes one scenario before the next.
- `--cap-usd`: see Spend. If the cap stops the run, report the count per scenario and stop; do not raise it.

### 5. M3 retrained (`e6/classify.py`, model C0 only)

- Train on all 25 scenarios. Drop old ordinary rows that fail the rule of step 3, in train and in val; report how
  many (planner's count: 157 of 880).
- Label space is 25. Keep the v1 model and its predictions as they are.

### 6. Tests and docs

- `pytest` passes. New enum values change how unlisted probability is spread, so pinned numbers may move: update a
  pinned number only when that is the cause, and list the tests you changed.
- `README.md` and `EXPERIMENTS.md`: a short "Catalogue v2" section. Earlier results stay as the v1 record.

## Spend

- Gemini only (`gemini-3.5-flash-lite`), step 4. Planner's estimate 0.8 USD (1.23 USD was measured for 3,300
  stories). Cap for this task: **1.0 USD**.
- Gemini budget left under the 25 USD cap is 0.73 USD, so this task needs Minh to raise it. Never raise a cap
  yourself.
- No server, no GPU, no other provider.

## Report

`experiments/T4/report.md` (English), real spend at the top, then:

- stories written per new scenario; rows dropped by the rule;
- C0 v2 on val, for `mo_dau` and `day_du`: accuracy overall and per scenario; scam called ordinary (k/n);
  ordinary called scam (k/n); every rate with a 95% Wilson interval;
- C0 v1 against C0 v2 on the val rows of the 15 old scenarios: did the 10 new scenarios cost accuracy;
- confusion: the 10 largest scenario pairs, plus `mo_vi_tra_sau_nhan_hoa_hong` with `ctv_online` and each new
  ordinary scenario with the scam named in its `doi_chieu_voi`;
- real narratives: C0 v2 on the 84 labelled ones, the 9 relabelled ones listed one by one, and what it answers
  for the 5 that stay `khac`;
- C0 v2 on the openings of the 300 v1 cases, next to the v1 figure;
- the chat prompt of `sim/run.py::run_tu_do` with 25 scenarios: tokens per turn (local tokenizer), next to the
  15-scenario figure;
- five generated stories per new scenario, picked by a seeded draw, for the planner to read.

## Deliverables

- Code, scenario files, tests, report, docs: committed and pushed.
- One line to the planner tab when done, or when stopped by the cap.
