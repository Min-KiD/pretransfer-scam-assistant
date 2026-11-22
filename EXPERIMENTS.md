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
| E4 | Can a small open vision model with LoRA read a screenshot into JSON as well as the closed API? (model M1) | Closed models, `qwen3-vl-4b`, `qwen3-vl-2b` done; `qwen3.5-4b` and LoRA running | Untrained `qwen3-vl-4b` finds 76.1% of real-screenshot strings vs 92.3% for the cheapest closed model, at 12 s/image on our GPU; `qwen3-vl-2b` finds 26.5%. M1 fails as defined: the 2 s/image limit is out of reach for any 2-4B model on an RTX 4060 Ti |
| E5 | Can a small open LLM run the conversation as well as closed models? (model M2) | Closed models, `qwen3-vl-4b`, `qwen3-vl-2b` done; `qwen3.5-4b` running | Closed models: 76-83% correct scenario on 75 sessions. On 300 sessions: `qwen3-vl-4b` 73.7%, `qwen3-vl-2b` 55.3%, vs 81.3% for `gemini-3.5-flash-lite`. M2 fails for both |
| E6 | Does a small CPU text classifier work as a second opinion on the scenario? (model M3) | Done for `gemini-3.5-flash-lite`, `qwen3-vl-4b`, `qwen3-vl-2b` sessions | TF-IDF + logistic regression (1.3 ms on CPU) catches 66-88% of the LLM's wrong conclusions and flags 4-8% of its correct ones: M3 kept |
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

Phase A, no training. Closed models are the reference; `qwen3-vl-4b` and `qwen3-vl-2b` are done and `qwen3.5-4b` is running. Three larger open models were dropped for disk space, not for results. Open models run on an RTX 4060 Ti 16GB through vLLM; J = JSON schema enforced while decoding, Ju = schema only in the prompt, O = PP-OCRv6 text instead of the image.

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

- **M1 fails for both untrained open models in all three modes.** On the 56-string test half: `qwen3-vl-4b` J 76.8% (43/56) vs 89.3% (50/56) for `gemini-3.5-flash-lite`, 12.5 points short (limit 5); the best `qwen3-vl-2b` mode (Ju) 37.5% (21/56).
- **`qwen3-vl-2b` breaks on real screenshots, not in general:** 81.2% (522/643) of strings on the 150 synthetic images drawn after real references, 26.5% on the real ones in J mode, where 20 of 56 outputs never close and most returned strings are not in the labels.
- **The 2 s/image part of M1 cannot be met on this GPU.** Measured decode speed for the 4B model at one request: about 31 output tokens/s; one screenshot's JSON is about 380 tokens (median), so 12 s. The 2B model takes 5.1 s (median, J). LoRA does not change speed. Plan: the product reads screenshots with `gemini-3.5-flash-lite`; LoRA is run to measure how much of the accuracy gap training closes, not to ship.
- **`qwen3-vl-4b` Ju's 1.8 s is not real speed:** without the enforced schema, it returned an empty JSON for 29 of the 56 real screenshots. On synthetic images Ju is as good as J (87.8% vs 87.2% on 172 strings), so the failure is specific to real screenshots.
- **OCR text instead of the image (O):** for `qwen3-vl-4b` it is lower than J on every set (within noise on the 40 synthetic images). For both models it returns the most strings that are not in our labels.
- **Same model, synthetic images:** 87.2% (150/172) on 40 images like our training data and 87.2% (561/643) on 150 images drawn after real reference screenshots. The drop to 76% on real screenshots is the domain gap LoRA has to close.
- **Valid JSON:** 100% for all four closed models. Of the 9 open-model failures on real screenshots, 8 are outputs that never close (text running on to the token limit) and 1 is an invalid escape.
- **The cheapest closed model finds the most strings but also returns the most extra ones.** For this product a wrong account number in a warning is worse than a missing one, so both columns count.
- **Part of the "extra" strings are gaps in our labels.** An audit found 9 places on the 56 images where two models agree with each other and not with the label. Not reviewed yet, so the second column is an upper bound.
- **Training data ready:** 4000 synthetic screenshots (7 app templates, 13 scenarios, random damage), 300 validation, and 300 held out with an unseen app template and 2 unseen scenarios.
- **LoRA, first numbers (synthetic validation only, 300 images, 900 strings):** untrained `qwen3-vl-4b` 80.1% (721/900) of strings found, 20.4% (190/930) returned strings not in the labels; LoRA on 500 images 87.0% (783/900), 7.8% (66/850); LoRA on 4000 images 93.0% (837/900), 6.1% (54/892) at its best checkpoint. This set looks like the training data, so it says the training works, not that real screenshots improve. Trained on a rented RTX 5090: 11.1 GiB peak memory, 38 min for one pass over 4000 images.
- **Next:** `qwen3-vl-2b` and `qwen3.5-4b` with no training; LoRA checkpoints picked on the real dev half, then scored on the real test half and the held-out set (unseen app template and scenarios).

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

- **Model size barely moves the scenario accuracy:** 76-83% on 75 sessions, all inside each other's intervals. The room for a small open model is there.
- **The cheapest model asks too little.** It concludes with no question in about half the sessions, and it misses the most scams (6 of 55). The larger models ask about one question and miss 0-1.
- **The E2 number reproduces:** 77.3% here vs 78.7% in E2 on the same 75 sessions.
- **M2 fails for `qwen3-vl-4b`:** 73.7% (221/300) vs 81.3% (244/300) correct scenario, 7.7 points short (limit 5). It asks 3.5x as many questions as `gemini-3.5-flash-lite` and still misses more scams (16 vs 10 of 220). Ordinary transfers flagged as scam: 7 of 80 for both. Valid output format: 993 of 993 turns.
- **`qwen3-vl-2b` is far behind:** 55.3% (166/300) correct scenario and 43 of 220 scams called ordinary.
- **Not run:** Claude (the API account has no credit). `qwen3.5-4b` is running.

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
- **Same rule behind the open models (300 sessions each):** for `qwen3-vl-4b`, C0 catches 50 of 71 wrong conclusions (70%) and flags 18 of 221 correct ones (8%); correct on concluded sessions goes from 75.7% to 90.6%, with 25.3% of sessions downgraded. For `qwen3-vl-2b`: 117 of 133 (88%) and 6 of 166 (4%); 55.5% to 90.9%, with 41.3% downgraded. M3 holds behind weaker LLMs, but the weaker the LLM, the more sessions end in "not enough evidence".
- **On real narratives the fine-tuned PhoBERT is clearly better** (88% vs 72%), but it is also confident on the 14 stories that fit no scenario (9 of 14 above 0.5), while C0 never is. C0 stays the second opinion; PhoBERT is worth retesting if the scenario list gets an "other" class.
- **Licence:** PhoBERT-base-v2 is AGPL-3.0; C0 has no such constraint.
- **Limits:** the training stories and the test sessions both come from one LLM family; 89 real narratives.

## Known gaps

- No real users anywhere. Simulated users are more cooperative than real ones.
- Real screenshots: 56 images, used for evaluation only.
- Open OCR setups ran on only the first 20 real screenshots; closed models ran on all 56. The two groups are not directly comparable on that set.
