# Experiments

Short log: what we tested, the main numbers, what we learned, what we decided. Raw outputs and long reports stay on our machines (`experiments/`, not in git).

Most numbers come from data we built ourselves and from simulated users. They are for choosing an approach, not for claiming quality on real users. Each configuration was run once.

## Overview

| ID | Question | State | Main finding |
|---|---|---|---|
| E1 | Can a model read account numbers, phones, links and amounts from a chat screenshot? Does separate OCR help? | Done | On clean screenshots everything is near 100% except links. Link errors are almost all `I` read as `l`; the domain is always right |
| E1b | Can open models on a 16GB GPU replace the closed API? What breaks on harder and real images? | Done | Open OCR reads text well, but no open model returned usable JSON. On real screenshots open OCR + regex falls to 51-61% |
| E2 | Should code pick the next question (information gain), or should the LLM ask freely? | Done, 2 runs | LLM asking freely is better: 78.7% vs 69.3% correct scenario. Code-picked questions dropped |
| E3 | How often is an ordinary transfer flagged as a scam? | Done | LLM asking freely: 1 of 20. Code-picked: 5 of 20 |
| E4 | Can a small open vision model with LoRA read a screenshot into JSON as well as the closed API? (model M1) | Done (phase B reduced: 500 and 4000 training images, no OCR-in-prompt run) | On the real test half, LoRA on 4000 synthetic images moves `qwen3-vl-4b` from 76.8% to 80.4% of strings found (intervals overlap) vs 89.3% for `gemini-3.5-flash-lite`; LoRA on 500 images makes real screenshots worse (60.7%). M1 fails: no open setup is within 5 points, and none gets near 2 s/image on an RTX 4060 Ti |
| E5 | Can a small open LLM run the conversation as well as closed models? (model M2) | Done | Closed models: 76-83% correct scenario on 75 sessions. On 300 sessions: `qwen3-vl-4b` 73.7%, `qwen3.5-4b` 69.3%, `qwen3-vl-2b` 55.3%, vs 81.3% for `gemini-3.5-flash-lite`. M2 fails for all three |
| E6 | Does a small CPU text classifier work as a second opinion on the scenario? (model M3) | Done | TF-IDF + logistic regression (1.3 ms on CPU) catches 66-88% of the LLM's wrong conclusions and flags 4-8% of its correct ones, behind all four LLMs tested: M3 kept |
| E10 | Do larger open chat models, more thinking, or Claude Haiku 5.5 close the gap? Should the chat model see the screenshot itself (merged) or the JSON read from it (split)? | Done | `gemma-4-e4b-qat` (open, 16 GB GPU) is the first open model to pass M2: 77.0% vs 81.3%, fewer ordinary transfers flagged. More thinking for `gemini-3.5-flash-lite` adds nothing. Haiku 5.5 chats as well as `gemini-3.5-flash-lite` and reads clean screenshots like `gemini-4-carbon`. With an image, split beats merged by 6.7 points; the app stays split |
| E11 | Does `gemini-3.8-flash` at high thinking call fewer scams ordinary, and at what cost? | Stopped by the cost projection after 30 of 75 sessions | 0.052 USD and 113 s per session, 14x the cost of low thinking. On the 30 sessions it ran, it is not more accurate (63.3% vs 76.7% at low, 83.3% for `gemini-3.5-flash-lite`) and ends 5 of 30 at "not enough evidence". The 30 hold only 10 scam cases, none called ordinary by any model, so the scam question is unanswered |
| T4 | Catalogue v2: 25 scenarios, a cleaner case generator, C0 (M3) retrained | Done | C0 on 25 scenarios: 73.1% / 77.7% correct on val (opening / full). The 10 new scenarios cost 2.8-4.2 points on the old 15. On real scams it calls 10 of 84 ordinary (v1 C0: 6 of the 75 old ones), 7 of them through the new ordinary look-alikes. The chat prompt grows by 1,439 tokens per call |
| T4b | Coherent stories: the generator draws only values the scenario lists, and every story states what the transfer is for. C0 retrained (v3) | Done | 5,250 new stories (`data/E6/cases_v2.jsonl`); 96% of openings name the purpose (old file: 56%). C0 v3 scores 99% on its own val, but every val story shares one of 78 purpose lines with train, so that score measures little. On real scams it is level with C0 v2 (63 vs 61 of 84 correct) and calls 12 of 84 ordinary (v2: 10), mostly a scam taken for its ordinary look-alike |
| T6 | Test set v2: 475 cases on the 25-scenario catalogue, written by GPT, and the first baseline on it | Done | `gemini-3.5-flash-lite`: 88.2% correct scenario after 3 questions. It calls 18 of 225 scams ordinary (8.0%) and flags 2 of 250 ordinary transfers (0.8%); 68% of sessions end without a question. Neither C0 v2 nor C0 v3 passes M3 as a second opinion behind it: at any confidence they disagree with 29-36% of the right conclusions |
| E7 | Label propagation on the account graph (model M4) | Not started | |
| E8 | A user who was coached by the scammer on what to answer | Not started | |
| E9 | Time and cost per session | Not started | |

## E1: reading strings from clean screenshots

- **Data:** 180 images. 30 chats rendered from HTML (Zalo, Messenger, SMS look) x 6 variants (original, dark, cropped, JPEG 40, half size, blurred). 756 strings, all made up. Links contain look-alike characters on purpose.
- **Tested:** PP-OCRv6 + regex; three Gemini models reading the image directly; the same models with the OCR text added to the prompt.

| Setup | Accounts | Phones | Links | Amounts | s/image | USD/1000 images |
|---|---|---|---|---|---|---|
| PP-OCRv6 (CPU) + regex | 100% | 100% | 68.7% | 100% | 20.0 | 0 |
| `gemini-3.5-flash-lite` | 95.6% | 100% | 68.2% | 100% | 5.8 | 1.53 |
| `gemini-3.5-flash-lite` + OCR text | 100% | 100% | 65.9% | 100% | 5.5 | 1.62 |
| `gemini-4-carbon` | 100% | 100% | 92.7% | 100% | 18.7 | 16.93 |

- **Links:** 50 of 55 errors or more are `I` vs `l`, which look the same in chat fonts. The domain was read correctly in 179/179 links by every setup; all errors are in the random path after `/`.
- **OCR as a cross-check:** it fixed all 8 dropped digits in account numbers for the cheapest model. It does not fix links, because OCR makes the same mistake.
- **Who said what:** 100% (1116/1116 messages) for every model.
- **Decisions:** the product uses only the domain of a link. OCR stays as a cross-check for account numbers when the vision model is small.
- **Limit:** this set is too easy to separate the approaches.

## E1b: open models, harder images, real images

- **Data:** the E1 set; 100 harder images (shrunk to 33%, saved twice as JPEG, photo of a screen, long chats); 40 images made by an image model; 20 real scam screenshots published by police and news sites (the set is now 56).
- **Tested on our 16GB GPU:** GLM-OCR, MinerU 2.5 Pro, PaddleOCR-VL 1.6, PP-OCRv6, each followed by regex; GLM-OCR also asked for JSON directly.

Strings found, all types together:

| Setup | E1 | Hard | Generated | Real (20) |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` (closed) | 91.4% | 89.7% | 93.0% | 83.7% (36/43) |
| GLM-OCR + regex | 96.4% | 94.6% | 84.3% | 60.5% |
| PP-OCRv6 GPU + regex | 92.9% | 91.8% | 83.7% | 58.1% |
| MinerU 2.5 Pro + regex | 90.5% (67 images) | 92.5% (43 images) | 89.0% | 55.8% |
| PaddleOCR-VL 1.6 + regex | 88.5% (121 images) | 88.3% (70 images) | 86.0% | 51.2% |
| GLM-OCR, image to JSON | 0% | 0% | 0% | 2.3% |

- **Reading text is solved by open models.** PP-OCRv6 takes 0.3 s/image on GPU, GLM-OCR about 4 s.
- **Image to JSON is not.** The one open model tried in JSON mode returned valid JSON for about a quarter of the images and no correct string. Qwen3-VL was not run here; that is E4.
- **Real screenshots are much harder than ours.** Most of the open-OCR misses are strings that are present in the OCR text but that our regex does not catch (`+84 86 ...`, wrapped links, bare domains, `8tr999k`). The weak part is the extraction step, not the OCR.
- **Decision:** train a small open vision model to output the JSON directly (M1), and keep PP-OCRv6 as a fast cross-check.
- **Limit:** 20 real images and 43 strings; one string is 2.3 points.

## E2 and E3: who chooses the questions

- **Data:** 75 simulated text-only sessions, 5 per scenario (11 scam, 4 ordinary). The simulated user is an LLM given a true story, a persona and an opening message.
- **Tested:** `computed` (code picks the field with the highest expected information gain, the LLM words the question and fills a story table); `computed, min 1 question`; `free` (the LLM reads the scenario descriptions and asks up to 3 questions on its own). All with `gemini-3.5-flash-lite`.

| After 3 questions | Correct scenario | Correct group (scam / ordinary) | Ordinary flagged as scam |
|---|---|---|---|
| `computed` | 69.3% | 89.3% | 5 of 20 |
| `computed`, min 1 question | 69.3% | 94.7% | 2 of 20 |
| `free` | 78.7% | 92.0% | 1 of 20 |

- **`free` wins by 9.3 points.** The rule set before the run was "keep `computed` only if it wins by 5 points", so it is dropped. Confidence intervals overlap (59-80 vs 69-88).
- **Why `computed` loses:** filling the story table from the user's first message over-infers. In 46 of 75 sessions it concluded with no question at all. Forcing one question did not help the final number.
- **Ceiling of the method:** with a simulated user who answers every field perfectly, `computed` reaches only 79.1%. Some scenarios are close by construction.
- **Over-inference is hard to prompt away.** Requiring a verbatim quote for every filled field cut "pressure" fills from 51 to 32 of 75 openings, but the model still quoted the user's own hurry as pressure from the other side.
- **False alarms cluster:** 4 of the 5 `computed` false alarms name "impersonating someone you know", triggered by "lending money to a friend".
- **Decision:** the LLM asks freely. The story table is kept as the structured output for the report to staff.
- **Limits:** the simulated user and the assistant are the same model; 5 cases per scenario; 20 ordinary cases give a very wide interval.

## E4: screenshot to JSON (M1)

No open setup is used in the product: it reads screenshots with `gemini-3.5-flash-lite`. Phase A has no training; closed models are the reference. Three larger open models were dropped for disk space, not for results. Open models run on an RTX 4060 Ti 16GB through vLLM; J = JSON schema enforced while decoding, Ju = schema only in the prompt, O = PP-OCRv6 text instead of the image. Phase B trains LoRA on `qwen3-vl-4b` with synthetic screenshots only.

Real screenshots, all 56 (117 strings):

| Model | Strings found | Returned strings not in our labels | Valid JSON | s/image | USD/1000 images |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 92.3% | 26.2% | 100% | 2.6 | 1.52 |
| `gemini-4-carbon` | 91.5% | 9.7% | 100% | 42.5 | 20.99 |
| `gpt-6.2-sol` | 82.1% | 11.0% | 100% | 8.3 | 10.05 |
| `gemini-3.8-flash`, low thinking | 79.5% | 16.3% | 100% | 6.6 | 2.66 |
| `qwen3-vl-4b`, J | 76.1% (89/117) | 25.0% (29/116) | 52 of 56 | 12.0 | own GPU |
| `qwen3-vl-4b`, O | 65.8% (77/117) | 46.0% (64/139) | 51 of 56 | 20.8 | own GPU |
| `qwen3-vl-4b`, Ju | 53.0% (62/117) | 16.9% (13/77) | 56 of 56 | 1.8 | own GPU |
| `qwen3-vl-2b`, Ju | 47.0% (55/117) | 60.0% (87/145) | 46 of 56 | 6.1 | own GPU |
| `qwen3-vl-2b`, O | 41.9% (49/117) | 84.1% (311/370) | 45 of 56 | 10.9 | own GPU |
| `qwen3-vl-2b`, J | 26.5% (31/117) | 77.6% (104/134) | 36 of 56 | 5.1 | own GPU |
| `qwen3.5-4b`, Ju | 82.9% (97/117) | 31.9% (45/141) | 56 of 56 | 14.8 | own GPU |
| `qwen3.5-4b`, O | 75.2% (88/117) | 56.9% (120/211) | 55 of 56 | 30.9 | own GPU |
| `qwen3.5-4b`, J | 66.7% (78/117) | 44.1% (64/145) | 54 of 56 | 12.8 | own GPU |
| `qwen3-vl-4b` + LoRA, 4000 images (step 125), J | 84.6% (99/117) | 24.2% (31/128) | 54 of 56 | 8.2 | own GPU |
| `qwen3-vl-4b` + LoRA, 500 images (step 63), J | 59.8% (70/117) | 19.0% (16/84) | 56 of 56 | 6.5 | own GPU |

- **M1 fails for every open setup (17 of 17).** On the 56-string test half: `gemini-3.5-flash-lite` 89.3% (50/56); `qwen3-vl-4b` J 76.8% (43/56), 12.5 points short (limit 5); with LoRA on 4000 images 80.4% (45/56) [68-89], 8.9 points short and 3.0 points more extra strings (limit 2); best untrained mode `qwen3.5-4b` Ju 78.6% (44/56). The LoRA rows on the dev half were used to pick the checkpoint, so the pooled 117-string rows above flatter LoRA slightly; the test half is the fair number.
- **`qwen3-vl-2b` breaks on real screenshots, not in general:** 81.2% (522/643) of strings on the 150 synthetic images drawn after real references, 26.5% on the real ones in J mode, where 20 of 56 outputs never close and most returned strings are not in the labels.
- **The 2 s/image part of M1 cannot be met on this GPU.** Measured decode speed for the 4B model at one request: about 31 output tokens/s; one screenshot's JSON is about 380 tokens (median), so 12 s. The 2B model takes 5.1 s (median, J). LoRA does not change decode speed; the LoRA model's 8.2 s comes from shorter answers (about 230 tokens). Plan: the product reads screenshots with `gemini-3.5-flash-lite`; LoRA is run to measure how much of the accuracy gap training closes, not to ship.
- **`qwen3-vl-4b` Ju's 1.8 s is not real speed:** without the enforced schema, it returned an empty JSON for 29 of the 56 real screenshots. On synthetic images Ju is as good as J (87.8% vs 87.2% on 172 strings), so the failure is specific to real screenshots.
- **OCR text instead of the image (O):** for `qwen3-vl-4b` it is lower than J on every set (within noise on the 40 synthetic images). For both models it returns the most strings that are not in our labels.
- **`qwen3-vl-4b` on synthetic images:** 87.2% (150/172) on 40 images like our training data and 87.2% (561/643) on 150 images drawn after real reference screenshots. The drop to 76% on real screenshots is the domain gap LoRA has to close.
- **Valid JSON:** 100% for all four closed models. Of the 9 `qwen3-vl-4b` failures on real screenshots (J and O), 8 are outputs that never close (text running on to the token limit) and 1 is an invalid escape.
- **The cheapest closed model finds the most strings but also returns the most extra ones.** For this product a wrong account number in a warning is worse than a missing one, so both columns count.
- **Part of the "extra" strings are gaps in our labels.** An audit found 9 places on the 56 images where two models agree with each other and not with the label. Not reviewed yet, so the second column is an upper bound.
- **Training data ready:** 4000 synthetic screenshots (7 app templates, 13 scenarios, random damage), 300 validation, and 300 held out with an unseen app template and 2 unseen scenarios.
- **LoRA on synthetic images (300 validation images, 900 strings; 300 held-out images with an unseen app template and 2 unseen scenarios, 942 strings):** untrained 80.1% (721/900) and 81.5% (768/942); 500 images 87.0% and 89.5%; 4000 images 92.3% (831/900) and 92.9% (875/942) at the picked checkpoint. Extra strings on validation fall from 20.4% (190/930) to 7.7% (70/905). Trained on a rented RTX 5090 (1.44 USD): rank 16 on all language-model projections, vision frozen, 11.4 GiB peak, 38 min for 4000 images.
- **On real screenshots LoRA helps only with enough data.** Real test half: untrained 76.8%, 500 images 60.7% (34/56), 4000 images 80.4% (45/56). After LoRA the model more often returns an empty or near-empty JSON on real screenshots (500 images: 9 of 56 with no message at all; one earlier checkpoint 22 of 56 fully empty), so its lower extra-string rate mostly means it returns less.
- **Checkpoint pick rule had a flaw:** it pooled validation (900 strings) with the real dev half (61 strings), so it picked almost by validation alone. Kept as declared; next time pick on the real dev half and use validation only to reject broken checkpoints.
- **OCR cross-check of account and phone numbers (B4):** flagging any returned number that PP-OCRv6 did not also read catches 4 of 15 wrong numbers on real screenshots and flags 0 of 25 correct ones (0-3 of ~360 on the synthetic sets). Many wrong numbers are real numbers in the image put under the wrong type (account vs phone), which this check cannot see.
- **Not run:** LoRA on 2000 images and LoRA with OCR text in the prompt (dropped for time); LoRA on `qwen3.5-4b`, which reads real screenshots better than `qwen3-vl-4b` untrained (Ju, dev half 86.9% vs 75.4%) but was not yet measured when the base was fixed.

## E5: conversation model (M2)

Same `free` assistant and prompt as E2. 300 simulated sessions (20 per scenario); the more expensive closed models ran only on the 75 sessions of E2.

| Model | Sessions | Correct scenario | Ordinary flagged as scam | Scam called ordinary | Questions asked | s/turn | USD/session |
|---|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 300 | 81.3% | 7 of 80 | 10 of 220 | 0.65 | 0.8 | 0.0011 |
| `gemini-3.5-flash-lite` | 75 | 77.3% | 1 of 20 | 6 of 55 | 0.69 | 0.8 | 0.0011 |
| `gemini-3.8-flash`, low thinking | 75 | 80.0% | 3 of 20 | 1 of 55 | 1.04 | 3.1 | 0.0033 |
| `gemini-4-carbon` | 75 | 82.7% | 3 of 20 | 1 of 55 | 1.37 | 19.2 | 0.0287 |
| `gpt-6.2-sol` | 75 | 76.0% | 1 of 20 | 0 of 55 | 1.11 | 1.8 | 0.0101 |
| `qwen3-vl-4b` (open, RTX 4060 Ti) | 300 | 73.7% | 7 of 80 | 16 of 220 | 2.31 | 1.6 | own GPU |
| `qwen3-vl-2b` (open, RTX 4060 Ti) | 300 | 55.3% | 4 of 80 | 43 of 220 | 2.29 | 0.9 | own GPU |
| `qwen3.5-4b` (open, RTX 4060 Ti) | 300 | 69.3% | 5 of 80 | 22 of 220 | 0.68 | 2.3 | own GPU |

- **Model size barely moves the scenario accuracy:** 76-83% on 75 sessions, all inside each other's intervals. The room for a small open model is there.
- **The cheapest model asks too little.** It concludes with no question in about half the sessions, and it misses the most scams (6 of 55). The larger models ask about one question and miss 0-1.
- **The E2 number reproduces:** 77.3% here vs 78.7% in E2 on the same 75 sessions.
- **M2 fails for `qwen3-vl-4b`:** 73.7% (221/300) vs 81.3% (244/300) correct scenario, 7.7 points short (limit 5). It asks 3.5x as many questions as `gemini-3.5-flash-lite` and still misses more scams (16 vs 10 of 220). Ordinary transfers flagged as scam: 7 of 80 for both. Valid output format: 993 of 993 turns.
- **`qwen3-vl-2b` is far behind:** 55.3% (166/300) correct scenario and 43 of 220 scams called ordinary.
- **`qwen3.5-4b`:** 69.3% (208/300), 12.0 points short. It asks as little as `gemini-3.5-flash-lite` (0.68 questions) and misses twice as many scams (22 vs 10 of 220).
- **Not run:** Claude (the API account has no credit).

## E6: scenario classifier as a second opinion (M3)

- **Data:** 3300 synthetic user stories written by `gemini-3.5-flash-lite` (15 scenarios x 220, 1.23 USD), each as an opening message and as opening + answers. Tested on the 300 E5 cases and on 89 real narratives (75 in the 11 scam scenarios, 14 outside them). Nothing from the test sets was used to train.
- **Tested:** C0 TF-IDF + logistic regression; C1 multilingual-e5-base without training (nearest scenario description); C2 PhoBERT-base-v2 fine-tuned; C3 multilingual-e5-small fine-tuned. The classifier for the second-opinion test was fixed in advance as the best on validation macro-F1: C0.

| Classifier | Validation | E5 cases, opening only | Real narratives (75) | Ordinary flagged as scam | ms/text CPU | Size |
|---|---|---|---|---|---|---|
| C0 TF-IDF + LR | 78.8% | 80.0% | 72.0% | 5 of 80 | 1.3 | 3.8 MB |
| C1 e5-base, no training | 50.7% | 59.7% | 74.7% | 13 of 80 | 65 | not measured |
| C2 PhoBERT-base-v2 | 77.0% | 81.0% | 88.0% | 4 of 80 | 62 | 542 MB |
| C3 e5-small | 75.3% | 75.7% | 72.0% | 8 of 80 | 17 | 488 MB |

Second opinion on the 300 `gemini-3.5-flash-lite` sessions, rule "if C0 disagrees, downgrade to *not enough evidence*":

| | Correct on concluded sessions | Downgraded | Ordinary flagged as scam | Scam called ordinary |
|---|---|---|---|---|
| LLM alone | 81.3% | 0% | 7 of 80 | 10 of 220 |
| LLM + C0 | 92.3% | 18.0% | 2 of 80 | 2 of 220 |

- **M3 is kept.** When C0 disagrees it catches 37 of the 56 wrong conclusions (66%, need 30%) and flags 17 of the 244 correct ones (7%, limit 15%).
- **The cost is 18% of sessions ending in "not enough evidence".** Applying the rule only when C0 is confident (top probability > 0.65, the threshold set on validation) catches only 6 of 56: confident disagreements are rare.
- **Same rule behind the open models (300 sessions each):** for `qwen3-vl-4b`, C0 catches 50 of 71 wrong conclusions (70%) and flags 18 of 221 correct ones (8%); correct on concluded sessions goes from 75.7% to 90.6%, with 25.3% of sessions downgraded. For `qwen3.5-4b`: 55 of 77 (71%) and 8 of 208 (4%); 73.0% to 90.1%, 26.0% downgraded. For `qwen3-vl-2b`: 117 of 133 (88%) and 6 of 166 (4%); 55.5% to 90.9%, with 41.3% downgraded. M3 holds behind weaker LLMs, but the weaker the LLM, the more sessions end in "not enough evidence".
- **On real narratives the fine-tuned PhoBERT is clearly better** (88% vs 72%), but it is also confident on the 14 stories that fit no scenario (9 of 14 above 0.5), while C0 never is. C0 stays the second opinion; PhoBERT is worth retesting if the scenario list gets an "other" class.
- **Licence:** PhoBERT-base-v2 is AGPL-3.0; C0 has no such constraint.
- **Limits:** the training stories and the test sessions both come from one LLM family; 89 real narratives.

## E10: larger open chat models, thinking level, Claude Haiku 5.5, merged vs split

Same 300 chat cases and simulated user as E5. Spend: Gemini 4.46 USD (22.71 of the 25 USD cap for E4-E10 used), Anthropic 2.28 USD.

| Chat model | Sessions | Correct scenario | Ordinary flagged as scam | Scam called ordinary | Questions asked | s/turn | USD/session |
|---|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` (E5) | 300 | 81.3% | 7 of 80 | 10 of 220 | 0.65 | 0.8 | 0.0011 |
| `gemma-4-e4b-qat` (open, RTX 4060 Ti) | 300 | 77.0% | 4 of 80 | 18 of 220 | 1.87 | 0.9 | own GPU |
| `qwen3-14b-awq` (open, RTX 4060 Ti) | 300 | 74.7% | 6 of 80 | 22 of 220 | 2.36 | 2.4 | own GPU |
| `qwen3-8b-fp8` (open, RTX 4060 Ti) | 300 | 70.3% | 4 of 80 | 17 of 220 | 2.54 | 2.0 | own GPU |
| `claude-haiku-5-5` | 300 | 81.7% | 6 of 80 | 4 of 220 | 1.30 | 3.7 | 0.0015 |
| `gemini-3.5-flash-lite`, medium thinking | 75 | 76.0% (77.3% at default) | 2 of 20 | 2 of 55 | 0.71 | 3.1 | 0.0049 |

- **M2 passes for `gemma-4-e4b-qat`** (Google's 4-bit QAT build, 11.6 GB, Apache-2.0): 4.3 points behind (limit 5) and fewer ordinary transfers flagged. It asks almost 3x as many questions and misses more scams (18 vs 10 of 220). The two larger Qwen3 models fail (6.6 and 11.0 points behind).
- **The C0 second opinion (E6) holds behind every new chat model:** it catches 53-74% of wrong conclusions and flags 4-8% of correct ones.
- **Gemma 4 cannot read screenshots:** 48.2% of strings found on real screenshots (vs 89.3% for `gemini-3.5-flash-lite`), half of what it returns is made up, and a quarter of schema-constrained calls fail.
- **Medium thinking for `gemini-3.5-flash-lite` adds nothing:** 76.0% vs 77.3% on the 75 E2 cases, at 4.3x the cost and 4x the time per turn. The 300-case run was stopped by the cost projection rule.
- **Claude Haiku 5.5:** chat accuracy equal to `gemini-3.5-flash-lite`, fewer scams missed, 4.7x slower per turn. As a screenshot reader it finds 95-99% of strings on synthetic and clean sets (`gemini-3.5-flash-lite` 90-93%, `gemini-4-carbon` 96-98%) at 1/20 of the price of `gemini-4-carbon`; on real screenshots 85.7% vs 89.3% for `gemini-3.5-flash-lite` (intervals overlap), with far fewer made-up strings (6 of 50 vs 22 of 69).

**Merged vs split** (300 cases with a synthetic screenshot, 20 per scenario; the opening message is neutral, so what happened is only in the image; the simulated user answers from the image's ground truth):

| Chat | What the chat model sees | Correct scenario | Ordinary flagged as scam | Scam called ordinary | Questions asked | First reply (s) |
|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | no image | 89.3% | 7 of 80 | 2 of 220 | 1.39 | 0.9 |
| `gemini-3.5-flash-lite` | split: JSON read by `gemini-3.5-flash-lite` | 93.3% (rerun 92.3%) | 6 of 80 | 1 of 220 | 0.28 | 3.7 |
| `gemini-3.5-flash-lite` | merged: the image itself | 86.7% | 14 of 80 | 2 of 220 | 0.65 | 1.6 |
| `claude-haiku-5-5` | split: JSON read by Haiku | 81.0% | 16 of 80 | 0 of 220 | 0.96 | 10.3 |
| `claude-haiku-5-5` | merged | 79.7% | 27 of 80 | 0 of 220 | 0.91 | 3.8 |
| `gemma-4-e4b-qat` (open) | split: same JSON as the `gemini-3.5-flash-lite` row | 89.3% | 4 of 80 | 5 of 220 | 2.27 | 4.3 |

- **The app stays split.** By the rule declared in advance, merged is 6.7 points behind split (paired interval -10.3 to -3.0; run-to-run noise of split 1.0 point). Merged is no better than no image at all; it is faster to the first reply and half the cost.
- **Haiku with a screenshot does not conclude "ordinary":** it gets 97% of scam cases right and never calls a scam ordinary, but only 25-30 of 80 ordinary transfers right; the rest are flagged as scam or left at "not enough evidence". Merged and split are equal for Haiku.
- **Closed reader + open chat stays within 5 points:** `gemma-4-e4b-qat` chatting on the `gemini-3.5-flash-lite` reads is 4.0 points behind (interval -7.7 to -0.3), about the same margin as in the text-only test, with fewer ordinary transfers flagged and more scams missed (5 vs 1 of 220).
- **Limits:** synthetic screenshots only (real ones have no scenario label); 41 of the 300 images come from the E4 training split (no E10 model was trained on them); many synthetic chats contain generic filler lines.

## E11: `gemini-3.8-flash` at high thinking

Question: Minh weighs "few scams called ordinary" above "few ordinary transfers flagged". At low thinking `gemini-3.8-flash` called 1 of 55 scams ordinary on the 75 E2 cases (`gemini-3.5-flash-lite`: 6 of 55). Does high thinking help, and what does it cost? Same protocol as E5, 75 cases planned, cap 1.8 USD, cost projected after 30 sessions.

- **Stopped at 30 sessions by the cost rule.** Projection 3.89 USD for 75 sessions (0.052 per session), over the 1.8 cap. Spent 1.556 USD. Cost per session has a long tail: median 0.017 USD, but one session cost 0.33 USD and took 695 s, and one call thought for 42,511 tokens.
- **The 30 sessions are not a fair sample.** The runner takes cases in id order, so they are the first 6 scenarios alphabetically: all 20 ordinary cases and only 10 of the 55 scam cases (2 of 11 scam scenarios). None of the three Gemini setups calls any of those 10 scams ordinary; every miss of the other two (1 and 6) is in the 45 cases not reached, so the main question stays open. A shuffled order would have given a representative 30.

| Model (same 30 cases) | Correct scenario | Ordinary flagged as scam | Scam called ordinary | `chua_du_can_cu` | Questions asked | s/session | USD/session |
|---|---|---|---|---|---|---|---|
| `gemini-3.8-flash`, high thinking | 63.3% | 3 of 20 | 0 of 10 | 5 of 30 | 1.17 | 113 | 0.0516 |
| `gemini-3.8-flash`, low thinking | 76.7% | 3 of 20 | 0 of 10 | 1 of 30 | 1.27 | 6.5 | 0.0037 |
| `gemini-3.5-flash-lite` | 83.3% | 1 of 20 | 0 of 10 | 0 of 30 | 0.70 | 1.4 | 0.0012 |

- **More thinking does not help on these cases.** High vs low: -13.3 points (paired interval -30.0 to 0.0, McNemar p=0.22). High vs `gemini-3.5-flash-lite`: -20.0 points (-36.7 to -6.7, p=0.03). Of its 11 wrong conclusions, 5 are "not enough evidence" (3 on the ordinary `bt_mua_online_nguoi_ban_moi`, 2 on the scam `bao_nguoi_than_cap_cuu`). No rule was declared in advance: on 30 cases this shows a direction; it decides nothing.
- **It is slow:** 60 s per call that asks a question, 43 s per call that concludes (p90 120 s and 71 s), so a user would wait minutes.
- **Spend:** the Gemini cap for E4-E11 now stands at 24.27 of 25 USD.

## Catalogue v2 (T4): 25 scenarios, cleaner case generator, C0 retrained

Why: too few scenarios, too large a scam share, and ordinary test cases that read like scams (data plan v2, `docs/specs/2026-11-26-data-plan-v2.md`, sections 3 and 3.7). Everything above was measured on catalogue v1 (15 scenarios) and stays as that record: the 300 cases in `sim/cases/` and the 3,300 E6 stories are unchanged.

- **Catalogue:** 15 to 25 scenarios (15 scam, 10 ordinary). 4 new scam types cover 9 of the 14 real narratives that matched no scenario (relabelled; 5 stay `khac`). 6 new ordinary scenarios are look-alikes of a scam, named in their `doi_chieu_voi` key. Schema: 4 new `tu_xung` values, 5 new `ly_do_tien` values, still 14 fields.
- **Generator (every case from now on, `sim/cases.py`):** the account label is drawn by group (ordinary: new 90%, reported 10%; scam: new 60%, reported 25%, confirmed 15%), no longer at random from five labels. An ordinary story table is redrawn while it carries a scam-type detail (install an app, read an OTP, top up to withdraw; money for a task, an investment, a "safe account", an error fix, a refund, a forwarded loan; told how to answer; threats or secrecy).
- **Stories:** 2,200 for the 10 new scenarios (220 each), written by `gemini-3.5-flash-lite` for 0.93 USD.
- **C0 v2** (TF-IDF + logistic regression, 25 labels; 157 of the 880 old ordinary stories dropped by the rule above):

| Input (val) | Correct scenario | Scam called ordinary | Ordinary called scam |
|---|---|---|---|
| Opening only | 73.1% (354/484) | 18 of 300 | 18 of 184 |
| Opening and answers | 77.7% (376/484) | 11 of 300 | 19 of 184 |

- **Cost of the 10 new scenarios on the old 15:** on the same val inputs, -4.2 points with the opening only (paired interval -7.0 to -1.4) and -2.8 with the answers (-5.3 to -0.4); 7% of those answers name a new scenario. On the openings of the 300 v1 cases: 77.3% vs 80.0% (-2.7, -5.3 to 0.0).
- **Real scams (84 labelled narratives):** 72.6% correct scenario; 7 of the 9 relabelled ones get their new label first. But C0 v2 calls 10 of 84 ordinary, against 6 of the 75 old ones for C0 v1 (C0 v2: 10 of those 75). 7 of the 10 go to new ordinary scenarios: loan repayment 3, bill to an organisation 2, paying the courier on delivery 1, own account 1.
- **Hardest new scenario:** the advance-fee loan scam (`vay_online_dong_phi_truoc`), 40% and 35% correct on val, mostly taken for fake bank, money-recovery service or fake authority.
- **Chat prompt:** the scenario list in the `tu_do` prompt grows from 1,582 to 3,021 tokens (Qwen3-4B tokenizer); the first-turn prompt from 1,876 to 3,315 tokens (+77%), paid on every call.

## Coherent stories (T4b): listed values only, a purpose for every story, C0 v3

Why: the T4 generator drew from the smoothed scenario table, so 35-55% of stories carried values the scenario does not list, and most stories never said what the money was for (23 of 220 advance-fee loan stories mentioned a loan).

- **Generator (`sim/cases.py`):** a listed field only takes listed values. Each case gets one of 3-4 purpose lines per scenario (`sim/viec_dang_lam.yaml`), and the opening must state it, rephrased. The writer sees every value in plain Vietnamese (`sim/gia_tri_bang_loi.yaml`). v1 cases and their text are unchanged.
- **Two pilots discarded.** In the first, 197 of 250 openings copied the purpose line word for word. In the second, users whose counterpart was a seller (`nguoi_ban`) called them a friend 13 times out of 17, because the raw id reads as "người bạn". After both fixes: 0 of 278 in the full file.
- **Stories:** 5,250 (190 train and 20 val per scenario). All of them hold listed values only, and 96% of openings name the purpose (keyword check; old file 56%, advance-fee loan 208/210 vs 22/220). Spend 2.27 USD of a 2.75 USD cap, pilots included.
- **C0 v3** (TF-IDF + logistic regression on the new file):

| Scored on | C0 v2 (old stories) | C0 v3 (new stories) |
|---|---|---|
| Old val, opening only | 73.1% | 59.9% |
| New val, opening only | 84.8% | 99.4% |
| 300 v1 openings | 77.3% | 77.3% |
| 84 real scams, correct scenario | 72.6% | 75.0% |
| 84 real scams, called ordinary | 10 | 12 |

- **What it means:** the new val shares its purpose lines with train, so 99% measures recall of 78 purposes. It does not measure stories told in other words. On real scams the two models are level (+2.4 points, -9.5 to +14.3). C0 v3 errs where a scam and its ordinary look-alike share a purpose: a deposit to a fanpage (homestay, villa, car) taken for a deposit after a viewing (4), an impersonated relative for a transfer to family (3), a fake courier for paying the courier on delivery (2).

## Test set v2 (T6): written by GPT, first baseline

Why: every chat number so far came from cases written by Gemini, the same family as the chat model, on the 15-scenario catalogue. From T6 on, chat numbers are measured on `sim/cases_v2/`. Nobody trains on it. The 300 v1 cases stay as the record.

- **Cases:** 475 (15 per scam scenario, 25 per ordinary scenario). Tables come from `sim.cases.make_case` (seed 20261128). `gpt-6.2-sol` wrote new purpose lines (none equal to a train line) and the openings. A batched `gpt-6.2-sol` re-read checked the ordinary openings against the scam catalogue. It dropped 1 of 250, which was replaced. No opening is identical to one in the train files, in v1, or elsewhere in the set.
- **Part A2:** the planner read the purpose lines. Three scam scenarios (`chuyen_nham_tien`, `gia_don_hang_lon_mua_ho`, `mo_vi_tra_sau_nhan_hoa_hong`) had drifted off their subject, because the prompt forbade paraphrasing the train lines. Their 45 cases were rewritten around a core purpose fixed by the planner; tables and ids are unchanged. Known limit: the `gia_don_hang_lon_mua_ho` lines are formulaic. OpenAI spend for A and A2: 1.33 USD of a 1.6 USD cap.
- **Simulated user (part B2):** stories with a purpose line now show the user the two account facts on the confirmation screen. Questions outside the table are answered from the scenario's `mo_ta`, else "not sure". Checked by eye on 60 fixed-question answers: 10 contradicted the facts or `mo_ta` with the old prompt, 3 with the new one.
- **Baseline**, `gemini-3.5-flash-lite`, `tu_do`, at most 3 questions, one run (Gemini 0.85 USD with the 45 pre-A2 sessions; cap 1.0):

| | Test set v2 (475) | v1 (E5, 300; not comparable) |
|---|---|---|
| Correct scenario after 3 questions | 88.2% (419) [85-91] | 81.3% (244) [77-85] |
| Scam called ordinary | 8.0% (18/225) [5-12] | 4.5% (10/220) [2-8] |
| Ordinary flagged as scam | 0.8% (2/250) [0-3] | 8.8% (7/80) [4-17] |
| Concluded without asking | 68.0% (323) [64-72] | 53.7% (161) [48-59] |
| Questions per session | 0.36 | 0.65 |
| USD per session (with simulated user) | 0.0016 | 0.0013 |

- **The two sets are not comparable.** v2 has 10 more scenarios, other writers and another simulated-user prompt. The 18 scams called ordinary are mostly scams taken for their ordinary look-alike: a cheap deposit for an online purchase from a new seller (6), a fake official for an organisation bill (3), and a fake courier for paying the courier on delivery (3). Weakest scenarios: `dich_vu_lay_lai_tien` 6/15 and `dat_coc_gia_re` 9/15.
- **Account label:** for scams labelled `da_xac_nhan`, 4 of 24 are called ordinary and only 16 of 24 get the right scenario (`moi`: 9 of 150 called ordinary, 131 of 150 right).
- **The 45 rewritten cases:** before A2, 28 of 45 got the right scenario and 7 were called ordinary; after A2, 45 of 45 and none. The new openings state the scam's mechanism outright (the core required it), so these 45 cases are now easy. [inference]
- **Second opinion (M3) is not met on v2.** At any confidence, C0 v2 disagrees with 68% of flash-lite's wrong conclusions, but also with 36% of its right ones; C0 v3 with 73% and 29%. Turning a disagreement into "not enough evidence" cuts the scams called ordinary to 3 (v2) or 7 (v3) of 225. But it does the same to 35-40% of all sessions. With the val-set threshold, C0 v2 (tau 0.8) never disagrees, because only 2 of 475 sessions reach 0.8. C0 v3 (tau 0.3) catches 4 of 56 wrong conclusions.
- **Classifiers alone on the openings:** C0 v2 54.9% correct, 28/225 scams called ordinary, 61/250 ordinary called scam; C0 v3 58.1%, 66/225 and 14/250. Report, split by group and account label: `experiments/T6/report.md` (`python3 -m e6.t6_report`).
- **Part D (image trial):** `gpt-image-2.6-sunburst` drew the first 5 `gen_moi` conversations of E1b with the same prompts and intended files (`data/E1b/gen_gpt/`, `python -m e1.gen_gpt`). Settings: 1024x1536, quality high, 1,372 output tokens and 0.043 USD per image, 27-43 s each; 0.21 USD of a 0.5 USD cap. Not yet read against the intended strings; the sonnet tab does that before any larger batch.

## Known gaps

- No real users anywhere. Simulated users are more cooperative than real ones.
- Real screenshots: 56 images, used for evaluation only.
- Open OCR setups ran on only the first 20 real screenshots; closed models ran on all 56. The two groups are not directly comparable on that set.
