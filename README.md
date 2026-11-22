# Pretransfer Scam Assistant

An assistant that steps in at the moment a wallet user is about to send money to a risky account. It asks what the transfer is for, reads a screenshot of the conversation that led to it, tells the user which known scam the situation resembles, and turns the exchange into a structured report for fraud staff.

Entry for MoMo Tech Contest 2026, topics "Anti-fraud" and "AI assistant".

**Status (22 Nov 2026):** research phase. A local sample app runs; the model experiments below are in progress; nothing is deployed yet. Design docs and task briefs are in Vietnamese.

| Date | What |
|---|---|
| 27 Nov, 23:59 | Team registration closes (2-3 members, no changes afterwards) |
| 3 Dec, 23:59 | Submission: live product link + 1-page guide, source `.zip`, 10 slides, 3-minute video |
| 3-11 Dec | Freeze: no changes, the app must stay online |
| 8 Dec | Top 5 announced |
| 11 Dec | Final in Ho Chi Minh City, in person |

## The problem

More than 90% of online-scam victims make the transfer themselves, under pressure from a story told on Zalo, Messenger, SMS or a phone call. A wallet app only sees the last step. It can flag a risky receiving account, but it does not know the story, so its warning is generic.

## What the product does

Two tiers:

- **Tier 1, the label at the confirm screen:** normal / yellow / red, from the receiving account's risk label plus a few rules. We treat this as an existing input (sample data in the demo). It is not what we measure.
- **Tier 2, right after the label appears (our work):**
  1. One question with tap-to-answer options: "What is this transfer for?" The user may attach a screenshot of the chat and may keep chatting.
  2. The assistant matches the story and the screenshot against a library of 15 scenarios (11 scams, 4 ordinary transfers), says which scam it resembles and why, what the scammer usually does next, and one thing to check.
  3. The user decides: stop, ask more, ask a staff member, or transfer anyway. The assistant never blocks.
  4. Every outcome becomes a structured report. When staff confirm it, the account's label changes and the next sender is warned earlier.

```mermaid
flowchart TD
    A[Enter account, amount, note] --> B{Tier 1: rules on the account label}
    B -- Known recipient --> Z[Transfer as usual]
    B -- New recipient --> C[One neutral line]
    B -- Yellow or red --> D[Warning card + one question with options]
    C --> D
    D --> E[Tier 2: read the screenshot, match story to scenarios]
    E --> F[Tailored warning + the scammer's usual next step]
    F --> G{User decides}
    G --> H[Stop]
    G --> I[Ask more]
    G --> J[Ask staff: summary is sent]
    G --> K[Transfer anyway]
    I --> F
    H --> L[Report -> staff review -> account label updated]
    J --> L
    K --> L
```

## Models

The demo should run on our own open models, not on a closed API. Closed models (Gemini, GPT, Claude) are used as reference points and as teachers for training data.

| Id | Model | Job | Trained on | Scored on | Experiment | State |
|---|---|---|---|---|---|---|
| M1 | Open VLM + LoRA, with PP-OCRv6 as a cross-check | Chat screenshot to JSON: messages, who said what, account numbers, phone numbers, links, amounts | Screenshots rendered from HTML (exact labels) | Real scam screenshots published by police and news sites | E4 | Running |
| M2 | Open LLM for the conversation (same base model as M1 if possible) | Ask follow-ups, pick the scenario, write the warning | Not trained yet; distillation only if E5 shows a gap | 300 simulated sessions | E5 | Running |
| M3 | Small text classifier on CPU | Second opinion on the scenario, with probabilities | Simulated user stories, labels set by us | Held-out simulated sessions + stories from real reported cases | E6 | Queued |
| M4 | Label propagation on the account graph | A confirmed report spreads to linked accounts | Sample data | No meaningful accuracy number; shows the mechanism only | - | Last, first to cut |

Keep-or-drop conditions for M1-M3 were written down before any numbers came in: [`docs/specs/2026-11-22-ke-hoach-model-va-thi-nghiem.md`](docs/specs/2026-11-22-ke-hoach-model-va-thi-nghiem.md), section 5.

## Results so far

All on small sets; they guide choices and are not quality claims. Details in [`EXPERIMENTS.md`](EXPERIMENTS.md).

- **Reading screenshots (E1, E1b):** on 20 real screenshots, `gemini-3.5-flash-lite` recovered 83.7% of the strings (36/43). Open OCR models followed by regex recovered 51-61%. The one open model run in image-to-JSON mode (GLM-OCR) scored 0%; Qwen3-VL and Gemma 4 were not run then. This gap is what M1 is meant to close.
- **Conversation (E2):** with at most 3 questions, the LLM asking freely named the right scenario in 78.7% of 75 simulated sessions and raised a false alarm on 1 of 20 ordinary transfers. Having code pick the questions by entropy scored 69.3% and was dropped.
- **Not measured yet:** anything with real users.

## What exists today

| Part | State |
|---|---|
| Scenario library, `scenarios/*.yaml` | 15 scenarios with sources, signs, what to check, the scammer's next steps |
| Core, `core/` | Session, scenario matching, image reading, account lookup on sample data. Calls Gemini today |
| Sample app, `app/` + `web/` | FastAPI + SQLite: transfer page with a chat panel, staff page that reviews reports and changes account labels. Plain HTML, local only |
| Simulator, `sim/` | An LLM plays the user from a fixed story; code scores the assistant. 300 cases in `sim/cases/` |
| Image experiments, `e1/` | Chat screenshot generator (HTML + Playwright), OCR/VLM runners, scoring |
| Not built yet | The two-tier UI above (wallet-style confirm screen, one-tap question, tier-specific buttons), open-model serving, deployment |

## Data

| Set | Size | What it is | Where |
|---|---|---|---|
| Scenarios | 15 | Scam and ordinary-transfer scenarios written from public police/news warnings | git, `scenarios/` |
| Simulated cases | 300 (15 x 20) | One simulated user each: true scenario, story table, persona, opening message | git, `sim/cases/` |
| `E1` screenshots | 180 | 30 HTML-rendered chats (Zalo, Messenger, SMS look) x 6 variants, exact labels | Drive, `data/E1/` |
| `E1b` hard screenshots | 100 | Downscaled, double-JPEG, re-photographed, long chats | Drive, `data/E1b/` |
| `gen` screenshots | 40 | Made by an image model, labels reviewed by eye | Drive, `data/E1b/gen/` |
| `web` real screenshots | 56 | Real scam chats/SMS published by police and news sites, with source URLs and string labels (all 56 labelled; experiment numbers so far cover the first 20). Evaluation only: never train on them, never republish | Drive, `data/E1b/real/` |
| Real reported cases | 89 | Scam cases from news/police reports: verbatim quote, summary, a first-person retelling from just before the transfer, scenario label | Drive, `data/narr/real/` |
| App recording notes | 35 frames | Layout notes of a wallet's transfer flow, used to design the sample UI | Not shared by default; ask Minh |

No real user data. All account numbers, phone numbers and names in generated sets are made up.

## Data and weights (Google Drive)

`data/` and model weights are not in git.

- **To share:** `./scripts/pack_data.sh` writes `../drive_upload/pretransfer-data-YYYYMMDD.tar.gz` (about 150 MB today). Upload that file to the team Drive folder.
- **To use:** download the archive and unpack it at the repo root: `tar -xzf pretransfer-data-YYYYMMDD.tar.gz`.
- **Weights:** base models are downloaded from Hugging Face by the scripts. Our own LoRA adapters and classifier weights will go in `weights/` (ignored by git, included in the archive once they exist).

## Repo map

| Path | Content |
|---|---|
| `docs/specs/` | Design and plan (Vietnamese). Start with `2026-11-22-ke-hoach-model-va-thi-nghiem.md` |
| `docs/tasks/` | One brief per task or experiment (Vietnamese) |
| `EXPERIMENTS.md`, `experiments/` | Summary and full report of each experiment |
| `scenarios/`, `core/`, `app/`, `web/`, `sim/`, `e1/`, `tests/` | See "What exists today" |
| `scripts/` | GPU-server pipelines, `pack_data.sh` |

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
./run_app.sh                       # sample app at http://localhost:8000/ , staff page at /web/staff.html
.venv/bin/python -m pytest -q      # unit tests, no model calls
.venv/bin/python -m sim.perfect    # scenario-matching ceiling, no API cost
```

`.env` (not in git) holds `GEMINI_API_KEY`, optionally `OPENAI_API_KEY`, `CLAUDE_API_KEY`, and `SERVER=user@host` for the GPU-server scripts. API budgets are capped; see section 7 of the plan before running anything that calls a paid model.

## Open questions for the team

- Does the two-tier split read as new, given that wallets already show receiver labels? Our claim is the step after the label, not the label.
- M4 (graph) is the weakest part. Keep, replace with something else, or cut?
- Which parts each person takes: sample-wallet UI, open-model serving and deployment, data collection and labelling, slides and video.
- Hosting from 3 to 11 Dec: a GPU has to stay online for three weeks. Not decided.
- More real screenshots and real cases are the most valuable data we can add by hand.

## Declarations required by the contest rules

Updated until submission.

| Item | Content |
|---|---|
| Pre-existing assets | None used so far |
| Open-source libraries | App and core: FastAPI, Starlette, Uvicorn, python-multipart, Pydantic, PyYAML, google-genai; tests: pytest, httpx. Image experiments: PaddleOCR, Playwright, Pillow, transformers |
| Open models tried | PP-OCRv6, PaddleOCR-VL 1.6, MinerU2.5-Pro, GLM-OCR; Qwen3-VL and Gemma 4 in E4 |
| Closed models and APIs | Gemini API, OpenAI API: reference points in experiments, and generation of synthetic training and test text. The image model `gemini-nano-banana-2.1` made the `gen` test screenshots |
| AI tools used to build | The coding assistant omp running Claude models: planning, documents, code |
| Infrastructure | A private GPU server (RTX 4060 Ti 16GB) for experiments; hosting for the submission not decided |
