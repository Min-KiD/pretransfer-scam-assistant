# E7 mock data, version 2 (`e7-synth-v2`)

This is the data set for the account-graph work (M4). It replaces version 1 (commit `2940796`): every number
measured on version 1 has to be measured again on this one.

Everything here is generated. No real account, phone number or report is used. A result on this data shows that
a mechanism works, not how it would perform on real traffic.

## 1. The flow the data is built for

- What the system works out by itself ends at **yellow** (a caution). **Red** comes only from a staff approval.
- Staff are not always there (no staff in the demo, days off, a daily limit), so a suspected account waits in a
  queue. Until someone approves it, every later customer who checks that account still gets yellow.
- Customer-facing yellow from the graph: the account shares a phone number or link with a staff-confirmed (red)
  account. It spreads from red only, never from yellow. Public phone numbers and links (marketplaces, carriers,
  hotlines) do not count.
- When staff clear an account it becomes "checked, normal" (`verified_normal`) and nothing spreads through it.
- A trained model only orders the staff queue. It does not put a label in front of a customer.

The data gives the world **as the app runs today, without M4**: reports arrive, the app raises yellow flags by
itself, staff review flagged accounts when they are at work. M4 is what you add on top and compare against it.

## 2. Files in one set

| File | One row is | Use |
|---|---|---|
| `accounts.jsonl` | a receiving account | input: `so_tk`, `loai`, `created_day`; answers: `gt_*` |
| `reports.jsonl` | one finished chat session about an account | input; answers: `gt_is_scam`, `gt_kich_ban` |
| `label_events.jsonl` | a label change of an account, in time order | input (what the system knew, and when) |
| `staff_calendar.jsonl` | one day: staff at work or not, capacity, accounts reviewed | input, and for replaying the staff loop |
| `public_entities.json` | a well-known public phone or link | input (the list used to drop public hubs) |
| `entities.jsonl` | a phone or link, with who really owns it | answers only (`gt_*`) |
| `graph_manifest.json` | settings, seed, summary counts, sha256 of every file | check |
| `sample_preview.json` | a few rows of each kind | reading by eye |

**Every field that starts with `gt_` is an answer.** Use it for scoring only, never as an input or to pick a
setting. `entities.jsonl` is answers as a whole.

### `accounts.jsonl`

| Field | Meaning |
|---|---|
| `so_tk` | account number (made-up prefix `0009`) |
| `loai` | `ca_nhan` (person) or `to_chuc` (organisation) |
| `created_day` | day the account first appears (1-90) |
| `gt_is_scam` | 1 if the account is used by a ring at any time |
| `gt_role` | `scam_organizer`, `scam_mule`, `hijacked_account`, `normal_merchant`, `normal_personal` |
| `gt_ring_id` | ring, shop group or family the account belongs to (`null` for single users) |
| `gt_is_heldout_ring` | 1 if its ring first appears after day 55 |
| `gt_hijack_day` | taken-over accounts only: ordinary up to this day, used by the ring after it |

### `reports.jsonl`

Same fields as the app's `reports` table, plus `day` and two answers. Rows are in time order and `id` grows with
time.

| Field | Meaning |
|---|---|
| `id`, `session_id` | report number (1 = earliest) and session name |
| `so_tk` | the account the customer was about to pay |
| `day`, `tao_luc` | day 1-90, and the time in days (`day - 1 <= tao_luc < day`) |
| `muc` | chat verdict: `giong_chieu_lua` (looks like a scam), `giong_binh_thuong` (looks ordinary), `chua_du_can_cu` (not enough to tell) |
| `kich_ban` | the scenario the chat named |
| `phan_phoi` | probabilities over the 25 scenarios; `kich_ban` is the highest |
| `nut` | what the customer pressed: `dung_lai` (stop), `kiem_tra_them` (check more), `van_chuyen` (transfer anyway) |
| `sdt`, `link` | phone numbers and link domains read from the chat screenshot |
| `so_tien` | amount in VND |
| `ten_khop_tu_xung` | `co` / `khong` / `null`: does the account type fit the role the other side claims |
| `gt_is_scam` | 1 if this session really was a scam |
| `gt_kich_ban` | the true scenario of the session |

### `label_events.jsonl`

| `by` | `label` | Meaning | Extra field |
|---|---|---|---|
| `bao_cao_tu_dong` | `dang_bi_bao_cao` | yellow flag raised by the app after a report with `muc = giong_chieu_lua` | `report_id` |
| `nhan_vien` | `da_xac_nhan` | staff approved: red | `flagged_day` |
| `nhan_vien` | `verified_normal` | staff cleared: checked, normal | `flagged_day` |

A staff event of day `d` happens at the end of day `d`: customers see it from day `d + 1`. The label of an account
on a given day is its latest event before that day. An account with no event has no label.

### `staff_calendar.jsonl`

`{"day", "working", "capacity", "reviewed"}`. Day 1 is a Monday; days 6 and 7 of every week are off. On a working
day nobody reviews with probability `staff_absence_prob`.

## 3. How a set is generated

1. **Public hubs.** 10 public link domains and 10 hotlines. 8 + 8 are in `public_entities.json`. Two domains
   (`tiktok.com`, `chotot.com`) and two hotlines (`19002345`, `18006789`) are public but **not in the list** and
   less popular, so they touch about as many accounts as a large ring's phone does.
2. **Scam rings.** Most rings have 6-13 accounts and 2-4 SIMs. About one ring in eight is large: 28-50 accounts,
   4-8 SIMs and one master phone that most of its accounts point to. Half of the rings also use 1-2 fake sites.
   About a quarter of the rings first appear after day 55. Rings that start earlier keep opening fresh accounts
   after day 55.
3. **Ordinary accounts.** Shop groups of 10-22 accounts around one shop phone (a third also have their own site);
   a few large groups of 30-45 accounts behind one dispatch phone; families of 3-6; single users.
4. **Taken-over accounts.** An ordinary personal account that a known ring starts using on `gt_hijack_day`.
5. **Reports.** Each account gets a few sessions. The screenshot reader misses a share of the strings
   (`m1_string_dropout`) and sometimes reads the customer's own number (`victim_phone_leak_prob`); those numbers
   connect scam and ordinary accounts by accident. Scam sessions sometimes show a public link or hotline too.
6. **Chat verdict.** For a session of true scenario S, the verdict (`muc`, `kich_ban`) is drawn from the endings
   a real chat model gave on our 475-case test set for scenario S (`e7/chat_confusion.json`, built by
   `e7/chat_confusion.py`). So the mock chat fails where the measured model fails. Example: with `flash_lite`, a
   `dat_coc_gia_re` scam is read as an ordinary purchase in 6 of 15 cases.
7. **Labels.** During the day, a report with `muc = giong_chieu_lua` puts a yellow flag on its account unless it
   is already yellow or red. At the end of each working day staff take the flagged accounts that have waited at
   least `staff_min_delay_days`, most scam verdicts first, then the oldest flag, and review up to
   `staff_capacity_per_day` of them. Staff are always right: red if the account is a scam account at that
   time, `verified_normal` otherwise. A cleared account gets a new yellow flag if a later report calls it a scam.

Phone numbers are random over the same prefixes for everyone: the digits say nothing about the owner.

## 4. The ten sets

8,000 accounts and 90 days each. Seed 20261127, except `holdout_mixed` (seed 20261203).

| Set | What differs from `base` | Scam accounts | Rings (large / first seen after day 55) | Reports | Yellow flags | Red | Checked normal | Still waiting on day 90 | Median days from flag to review |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| `base` | - | 360 | 26 (3 / 6) | 9,051 | 428 | 153 | 12 | 263 | 6 |
| `s1_hub_explosion` | public links and hotlines in far more sessions | 360 | 26 (3 / 6) | 8,953 | 411 | 155 | 9 | 247 | 5 |
| `s2_high_heterophily` | more customer numbers read by accident, more taken-over accounts | 360 | 23 (3 / 6) | 9,057 | 422 | 160 | 2 | 260 | 6 |
| `s3_heavy_noise` | reader misses more strings; chat = untrained Qwen | 360 | 26 (3 / 6) | 9,053 | 609 | 146 | 19 | 444 | 6 |
| `s4_sparse_imbalance` | 2% scam accounts; staff review 1 a day | 160 | 11 (2 / 3) | 8,696 | 229 | 54 | 3 | 172 | 9 |
| `s5_camouflage_drift` | scam sessions carry more public strings; more late rings | 360 | 26 (3 / 9) | 9,074 | 426 | 149 | 14 | 263 | 5 |
| `s6_cold_start_heavy` | half of the rings first appear after day 55 | 360 | 26 (3 / 13) | 9,047 | 429 | 138 | 23 | 268 | 5 |
| `s7_slow_staff` | same reports as `base`; staff 1 a day, absent 35% of days, 3-day minimum wait | 360 | 26 (3 / 6) | 9,051 | 428 | 41 | 0 | 387 | 22 |
| `s8_chat_qwen_lora` | same accounts as `base`; chat = Qwen + LoRA (Run B) | 360 | 26 (3 / 6) | 9,051 | 584 | 153 | 15 | 416 | 6 |
| `holdout_mixed` | other seed, several settings changed at once | 360 | 20 (4 / 7) | 8,991 | 419 | 111 | 1 | 307 | 7 |

`holdout_mixed` is for the final score only. Do not look at it while choosing a method or a setting.

Why staff review 3 accounts a day in `base`: about 4.8 new yellow flags arrive per calendar day, so the queue
grows and the order of the queue matters (with 2 a day only 5 ordinary accounts are ever cleared and the median
wait is 8 days; with 5 a day 44 are cleared and the median wait is 3 days).

Sessions per chat table on `base`-sized sets: with `flash_lite` about 6% of scam sessions are called ordinary and
0.9% of ordinary sessions are called scams; `qwen_untrained` 13% and 3.3%; `qwen_lora` 3% and 2.9%.
`chua_du_can_cu` is rare in all three (0, 1 and 7 sessions).

In every set, both sides have phones or links on more than 20 accounts (`base`: 9 ring entities up to 37
accounts, 10 shop phones up to 36, unlisted public hubs on 15-45, listed public hubs on 117-301). A degree cap
alone, or the public list alone, does not separate them.

## 5. Scoring that fits the flow

Score **customer sessions**, not accounts: each report of days 71-90 is one customer about to pay.

For each such session, using only what was known before it (reports with a smaller `id`, label events of earlier
days):

1. What does the customer see when the account number is typed (red, yellow, nothing)?
2. What does the customer see after the screenshot is read (the session's own `sdt` and `link` can be looked up)?

Report, split by `gt_is_scam`, and for scams also by known ring / ring first seen after day 55:

- share of scam sessions that got a warning (yellow or red) before the transfer;
- share of ordinary sessions that got a warning.

Compare four rows on the same sessions:

1. no M4 (labels from `label_events.jsonl` only);
2. the one-step rule (shares a non-public phone or link with a red account);
3. the trained model ordering the staff queue;
4. the same staff capacity with the default queue order (this is the data as given).

Rows 3 and 4 need the staff loop replayed with a different order: walk the days of `staff_calendar.jsonl`, raise
yellow flags from the reports yourself, pick up to `capacity` waiting accounts in your own order, and take the
outcome from `e7.gen_graph.staff_outcome(account, day)`. `e7.gen_graph.simulate_labels` is the reference loop.
Calling `staff_outcome` is the only allowed use of the answers before scoring.

Rules:

- Thresholds and settings are chosen with staff labels (`label_events.jsonl`) only, never with `gt_*`.
- Choose on one set, report on others; give the `holdout_mixed` number last.
- More than one seed for anything quoted (`python -m e7.gen_graph --preset base --seed N`).

## 6. Known limits

- Generated data: rings, shops and hubs behave the way the generator says they do.
- Chat tables come from 15 scam or 25 ordinary test cases per scenario. They are coarse, and an ending that never
  occurred in those cases never occurs here.
- The chat verdict does not react to the account's label at the time (in the app the label is shown to the chat).
- Staff are always right and always follow the same queue order.
- Sessions do not react to warnings: a ring keeps using an account after it turns red.
- The planner's quick check of the one-step rule on `base` (public list plus a cap of 60 accounts per phone or
  link, days 71-90; a check that the data behaves, not a result): scam sessions warned after the screenshot 96%
  against 65% from labels alone at account entry; ordinary sessions warned 7.7% against 0.3%. Most of the 7.7%
  comes through customer numbers read by accident and unlisted public hubs.

## 7. Commands

```bash
python -m e7.gen_graph --preset base --seed 20261127 --out data/E7/base
python -m e7.gen_graph --preset holdout_mixed --seed 20261203 --out data/E7/holdout_mixed
python -m pytest tests/test_e7.py -q
```

Changes against version 1: 8,000 accounts instead of 3,000; large rings and large shop groups; unlisted public
hubs and `public_entities.json`; chat verdicts from measured tables instead of random rates; `m3_scam_prob`
removed (that model is not in the app); `gt_is_scam` and `gt_kich_ban` on reports; report ids in time order;
`hijack_day` renamed `gt_hijack_day`; staff reviews over all 90 days with `verified_normal`, replacing
`confirmed_scam_frac` and `verified_normal_frac`; no role-specific phone prefixes; presets `s7_slow_staff`,
`s8_chat_qwen_lora`, `holdout_mixed` added.
