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

## Part A2 - Purpose lines of three scam scenarios rewritten (added 2026-11-26 after the planner read Part A)

The planner read all 225 scam purpose lines and the openings of five scenarios, before seeing any Part C result.
Twelve scam scenarios are on their subject. Three drifted, because the planner's instruction "do not paraphrase the
train lines, cover other situations" cannot be met where the scam has one purpose only:

- `chuyen_nham_tien`: most lines are another payment ("Trả tiền cọc phòng theo mã QR của cô chủ trọ", "Gửi 180 nghìn
  tiền cơm trưa vào tài khoản của chị thu ngân"). Openings 0, 9 and 14 never mention money sent by mistake; most of
  the others join two unrelated stories.
- `gia_don_hang_lon_mua_ho`: the lines lost "buying on behalf of a customer, from the supplier the customer named"
  ("Tôi trả tiền cho thợ sửa khóa tủ đồ", "Tôi trả tiền thuê xe nâng").
- `mo_vi_tra_sau_nhan_hoa_hong`: several lines lost "the money sent is the money just borrowed or advanced"
  (cases 0, 3, 7, 13).

Redo for these three scenarios only (45 cases, about 0.15 USD OpenAI; the Part A cap becomes 1.6 USD):

- Same tables, personas and ids (same `make_case` seed); only `viec` and `tin_mo_dau` are new. Move the 45 old
  files to `sim/cases_v2/_replaced/` and keep their Part C sessions.
- `VIEC_PROMPT` for these three: drop "không viết lại chúng theo cách khác; hãy nghĩ ra những hoàn cảnh cụ thể khác
  cùng loại"; say instead "không chép nguyên văn" and add the line "Mỗi dòng phải giữ đúng việc cốt lõi sau, chỉ đổi
  hoàn cảnh cụ thể: <core>", with these cores (use them verbatim):
  - `chuyen_nham_tien`: "Người dùng đang trả lại một khoản tiền lạ vừa vào tài khoản của mình, vì có người liên lạc
    nói là họ chuyển nhầm. Dòng nào cũng phải nói rõ đây là trả lại tiền người ta chuyển nhầm. Đổi số tiền, cách
    người kia liên lạc, nơi được bảo trả về (một số tài khoản khác, mã QR, đường link), hoặc việc khoản tiền bị gọi
    là tiền vay và bị đòi thêm lãi."
  - `gia_don_hang_lon_mua_ho`: "Người dùng là người bán hàng hoặc làm dịch vụ, đang chuyển tiền cọc hoặc tiền hàng
    cho một nhà cung cấp do chính vị khách đặt đơn lớn giới thiệu, để lấy hộ khách món hàng mình không có sẵn.
    Dòng nào cũng phải nói rõ là mua hộ hoặc lấy hàng hộ khách đặt đơn, và bên nhận tiền là chỗ khách giới thiệu.
    Đổi loại cửa hàng, món hàng, đơn vị của khách (doanh trại, bệnh viện, trường học), khoản tiền."
  - `mo_vi_tra_sau_nhan_hoa_hong`: "Người dùng đang chuyển chính số tiền vừa vay hoặc vừa được ứng (ví trả sau, vay
    nhanh trên ví, hạn mức mua trả góp) cho người hoặc 'dịch vụ' đã hướng dẫn mình, để nhận hoa hồng, ưu đãi, hoặc
    vì được hứa sẽ hủy khoản vay. Dòng nào cũng phải nói rõ tiền chuyển đi là tiền vừa vay hoặc vừa được ứng. Đổi
    nguồn tiền, người hướng dẫn, lời hứa, khoản tiền."
- Write the 45 new lines and openings (next to the old ones) to `experiments/T6/a2.md`, send the planner one line
  and **wait for "A2 ok"** before running Part C on them. Part C on the other 430 cases goes on meanwhile.
- Report: the main Part C tables use the 475 cases with the 45 new ones. One extra table gives the same rows on the
  45 replaced cases, so the effect of the rewrite is visible.

## Part B - Runner

- `sim/e5.py`: a flag for the case directory and a seeded stratified order (round-robin over scenarios, seed
  flag). Results of this task go to `experiments/T6/`, never into `experiments/E5/`.
- Protocol unchanged: `tu_do` prompt, at most 3 questions, simulated user `gemini-3.5-flash-lite`.

## Part B2 - Simulated user must not invent details (added 2026-11-26; do this before Part C)

Found in the Sonnet teacher trial (`data/T5/trial.jsonl`): the assistant asks things the story table does not hold
("where did you get this account number", "whose name shows as the account holder"), and the simulated user
invents an answer, often a warning sign, on ordinary stories. Three examples: `e6_bt_hoa_don_to_chuc__75` ("the
number the teacher sent by SMS differs from the school's notice, and the name is her personal name", while the
account line says organisation, name matches); `e6_bt_tra_no_khoan_vay__94` ("the number came over Zalo, I do not
know whose name"); `e6_bt_tra_no_khoan_vay__177` ("a staff member sent the number by SMS"). The teacher then
answers `chua_du_can_cu`, correctly for that dialogue. In the trial 7 of the 27 ordinary sessions outside
`bt_mua_online_nguoi_ban_moi` ended in `chua_du_can_cu`; the planner read these three, not all seven. Every chat
measurement uses this simulated user, so fix it first.

Change, for cases that carry `viec` only (v1 cases keep the old prompt byte for byte):

- The story block of `VICTIM_PROMPT` also gets the two account facts the user can see on the confirmation screen,
  in plain words: account type (personal or organisation) and whether the holder's name matches who the other
  side says they are.
- Replace the rule "only tell what is in the true story; otherwise say you do not know" with three steps: asked
  about something in the true story, answer from it; not in the true story but stated in the general situation
  (`mo_ta`: where the account number came from, what was already checked, whether goods were received), answer
  as the general situation says, in your own words; in neither, say you do not know or have not checked. Never
  invent a new detail (another account number, another name, an extra fee, a contract). The rules on persona,
  length and not saying "lừa đảo" stay.
- Check before Part C, about 0.05 USD: 40 ordinary and 20 scam `val` rows of `data/E6/cases_v2.jsonl` (seeded,
  round-robin), one fixed question after the opening: "Bạn lấy số tài khoản này từ đâu, và tên chủ tài khoản hiện
  lên là tên ai?", answered with the old and the new prompt. Write all 120 answers with the account facts and
  `mo_ta` to `experiments/T6/victim_check.md`, count by eye the answers that contradict the account facts or
  `mo_ta`, and send the planner the two counts in one line. Continue to Part C without waiting unless the new
  prompt contradicts in more than 5 of 60.
- The `sonnet` tab imports `victim_reply` and `VICTIM_PROMPT`; tell the planner the commit so it can re-run its
  trial.

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
