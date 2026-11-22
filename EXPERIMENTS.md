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
| E4 | Can a small open vision model with LoRA read a screenshot into JSON as well as the closed API? (model M1) | Closed baselines done; open models running | Closed baseline on 56 real screenshots: 92.3% of strings found, but 26.2% of returned strings are not in our labels |
| E5 | Can a small open LLM run the conversation as well as closed models? (model M2) | Closed baselines done; open models running | Closed models: 76-83% correct scenario on 75 sessions. The cheapest one is within noise of the best |
| E6 | Does a small CPU text classifier work as a second opinion on the scenario? (model M3) | Data and code ready, not run | |
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

Phase A, no training. Closed models are the reference; the open models (`qwen3-vl-4b`, `qwen3.5-4b`, `qwen3-vl-2b`) are running. Three larger open models were dropped for disk space, not for results.

Real screenshots, all 56 (117 strings):

| Model | Strings found | Returned strings not in our labels | s/image | USD/1000 images |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 92.3% | 26.2% | 2.6 | 1.52 |
| `gemini-4-carbon` | 91.5% | 9.7% | 42.5 | 20.99 |
| `gpt-6.2-sol` | 82.1% | 11.0% | 8.3 | 10.05 |
| `gemini-3.8-flash`, low thinking | 79.5% | 16.3% | 6.6 | 2.66 |

- **The cheapest closed model finds the most strings but also returns the most extra ones.** For this product a wrong account number in a warning is worse than a missing one, so both columns count.
- **Part of the "extra" strings are gaps in our labels.** An audit found 9 places on the 56 images where two models agree with each other and not with the label. Not reviewed yet, so the second column is an upper bound.
- **Valid JSON:** 100% for all four closed models.
- **Training data ready:** 4000 synthetic screenshots (7 app templates, 13 scenarios, random damage), 300 validation, and 300 held out with an unseen app template and 2 unseen scenarios.
- **Next:** open models with no training, then LoRA, scored on the half of the real set that nobody has looked at.

## E5: conversation model (M2)

Same `free` assistant and prompt as E2. 300 simulated sessions (20 per scenario); the more expensive closed models ran only on the 75 sessions of E2.

| Model | Sessions | Correct scenario | Ordinary flagged as scam | Scam called ordinary | Questions asked | s/turn | USD/session |
|---|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 300 | 81.3% | 7 of 80 | 10 of 220 | 0.65 | 0.8 | 0.0011 |
| `gemini-3.5-flash-lite` | 75 | 77.3% | 1 of 20 | 6 of 55 | 0.69 | 0.8 | 0.0011 |
| `gemini-3.8-flash`, low thinking | 75 | 80.0% | 3 of 20 | 1 of 55 | 1.04 | 3.1 | 0.0033 |
| `gemini-4-carbon` | 75 | 82.7% | 3 of 20 | 1 of 55 | 1.37 | 19.2 | 0.0287 |
| `gpt-6.2-sol` | 75 | 76.0% | 1 of 20 | 0 of 55 | 1.11 | 1.8 | 0.0101 |

- **Model size barely moves the scenario accuracy:** 76-83% on 75 sessions, all inside each other's intervals. The room for a small open model is there.
- **The cheapest model asks too little.** It concludes with no question in about half the sessions, and it misses the most scams (6 of 55). The larger models ask about one question and miss 0-1.
- **The E2 number reproduces:** 77.3% here vs 78.7% in E2 on the same 75 sessions.
- **Not run:** Claude (the API account has no credit). Open models are running.

## Known gaps

- No real users anywhere. Simulated users are more cooperative than real ones.
- Real screenshots: 56 images, used for evaluation only.
- Open OCR setups ran on only the first 20 real screenshots; closed models ran on all 56. The two groups are not directly comparable on that set.
