#!/usr/bin/env bash
# E6 on the server: train the four classifiers (GPU for C2/C3 when nobody else uses it), then predict every test input.
#
#   bash scripts/e6_server.sh --detach            # train (skips models already in data/E6/models.json) + predict
#   STEP=predict bash scripts/e6_server.sh --detach   # predict only (after new E5 sessions arrive)
#
# Needs data/E6/cases.jsonl (sim/e6_data.py, run on the laptop) and experiments/E5/sessions.jsonl synced here.
# Weights: .cache/e6/<model>/ (not committed). Log: .cache/logs/e6/e6.log
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e6
mkdir -p "$LOGS"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup env STEP="${STEP:-all}" bash "$0" > "$LOGS/e6.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/e6.log"
  exit 0
fi
exec 7> "$LOGS/e6.lock"
flock -n 7 || { echo "another e6_server.sh is running"; exit 1; }
export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
VPY=$ROOT/.venv-e4/bin/python
STEP=${STEP:-all}
log() { echo "[$(date -u +%T)] $*"; }
gpu_busy() { [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]; }

until python3 -c "import json,sys; sys.exit(0 if json.load(open('.cache/logs/e4/part0_status.json'))['env']['state']=='done' else 1)" 2>/dev/null; do
  log "waiting for .venv-e4 (scripts/e4_part0.sh)"; sleep 300
done
"$VPY" -c "import sklearn, pyvi" 2>/dev/null || "$ROOT/.venv-e4/bin/pip" install -q "scikit-learn==1.9.1" "pyvi==0.1.1" \
  || { log "pip install failed"; exit 1; }
if [[ $STEP == all ]]; then
  for m in c0 c1 c2 c3; do
    if "$VPY" -c "import json,sys; sys.exit(0 if 'train' in json.load(open('data/E6/models.json')).get('$m',{}) else 1)" 2>/dev/null; then
      log "$m already trained"; continue
    fi
    dev=cpu
    if [[ $m == c2 || $m == c3 ]]; then
      while gpu_busy; do log "$m waiting: GPU in use"; sleep 300; done
      dev=cuda
    fi
    log "train $m on $dev"
    "$VPY" -m e6.classify train --model "$m" --device "$dev" || log "train $m failed"
  done
fi
for m in c0 c1 c2 c3; do
  log "predict $m"
  "$VPY" -m e6.classify predict --model "$m" --device cpu || log "predict $m failed"
done
log done
