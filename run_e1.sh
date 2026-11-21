#!/usr/bin/env bash
# E1 end to end, from the laptop: generate data -> sync -> OCR + Gemini on the server -> pull back -> score.
# Needs locally: python3 with playwright + Pillow, Google Chrome (or `playwright install chromium`).
# Needs on the server: env at $REMOTE/.conda/pretransfer (see experiments/E1/report.md) and $REMOTE/.env with GEMINI_API_KEY.
# Steps are cached; FRESH=1 deletes data/E1 (images, OCR and API results) first.
# Long runs: start the server part detached instead (scripts/server_run.sh --detach, then scripts/server_status.sh).
set -euo pipefail
SERVER=${SERVER:-$(sed -n 's/^SERVER=//p' "$(dirname "$0")/.env" 2>/dev/null)}   # user@host of the GPU server; kept in .env, not in git
: "${SERVER:?set SERVER=user@host (env var or a SERVER= line in .env)}"
REMOTE=${REMOTE:-pretransfer-scam-assistant}
cd "$(dirname "$0")"

if [[ "${FRESH:-0}" == 1 ]]; then
  rm -rf data/E1
  ssh "$SERVER" "rm -rf $REMOTE/data/E1"
fi
[[ -f data/E1/manifest.jsonl ]] || python3 -m e1.gen_data --out data/E1

rsync -a --exclude .env --exclude .git/ --exclude .conda/ --exclude .cache/ --exclude __pycache__/ \
  --exclude experiments/ --exclude findings.md ./ "$SERVER:$REMOTE/"
ssh "$SERVER" "cd $REMOTE && bash scripts/server_run.sh"
rsync -a "$SERVER:$REMOTE/data/E1/ocr" "$SERVER:$REMOTE/data/E1/runs" "$SERVER:$REMOTE/data/E1/env.json" data/E1/

python3 -m e1.score --data data/E1 --out experiments/E1
