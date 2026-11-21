#!/usr/bin/env bash
# E1 server pipeline: check env -> OCR (A) -> Gemini B -> Gemini C -> score into experiments/E1.
# Every step is cached (finished images are skipped), so re-running only does what is missing.
#
#   bash scripts/server_run.sh --detach   # start in the background (setsid + nohup); survives SSH drops
#   bash scripts/server_run.sh            # run in the foreground
#
# Progress: .cache/logs/status.json (written after every step) and .cache/logs/<step>.log.
# A failing step stops the pipeline and records its exit code and last log lines; nothing is retried here.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs
STATUS=$LOGS/status.json
PY=$ROOT/.conda/pretransfer/bin/python
# Gemini models for B and C, all with the same schema and default settings.
MODELS=${MODELS:-"gemini-3.5-flash-lite gemini-3.8-flash gemini-4-carbon"}
WORKERS=${WORKERS:-6}
MAX_MEAN_SECONDS=${MAX_MEAN_SECONDS:-60}   # stop a model early if it averages slower than this per image
INSTALL_WAIT_MIN=${INSTALL_WAIT_MIN:-30}
mkdir -p "$LOGS"

if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" > "$LOGS/server_run.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/server_run.log status=$STATUS"
  exit 0
fi

exec 9> "$LOGS/server_run.lock"
flock -n 9 || { echo "another server_run.sh is running"; exit 1; }

# paddle writes to ~/.cache/paddle and ~/.paddlex regardless of settings: keep $HOME inside the project.
export HOME=$ROOT/.cache/home PADDLE_PDX_CACHE_HOME=$ROOT/.cache/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
mkdir -p "$HOME"
STARTED=$(date -u +%FT%TZ)
DONE_STEPS=""

status() {  # state step exit_code last_error
  STATE="$1" STEP="$2" CODE="$3" ERR="$4" STARTED="$STARTED" DONE_STEPS="$DONE_STEPS" STEP_START="${STEP_START:-}" \
  python3 - "$STATUS" <<'EOF'
import json, os, sys, datetime
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
s = {"state": os.environ["STATE"], "step": os.environ["STEP"], "pipeline_started": os.environ["STARTED"],
     "step_started": os.environ["STEP_START"] or None, "updated": now,
     "finished": now if os.environ["STATE"] in ("done", "failed") else None,
     "exit_code": int(os.environ["CODE"]) if os.environ["CODE"] else None,
     "last_error": os.environ["ERR"] or None, "steps_done": os.environ["DONE_STEPS"].split()}
json.dump(s, open(sys.argv[1] + ".tmp", "w"), indent=1)
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
EOF
}

run() {  # name cmd...
  local name=$1; shift
  STEP_START=$(date -u +%FT%TZ)
  status running "$name" "" ""
  echo "[$(date -u +%T)] >>> $name: $*"
  "$@" > "$LOGS/$name.log" 2>&1
  local code=$?
  if [[ $code -ne 0 ]]; then
    status failed "$name" "$code" "$(grep -v -i warn "$LOGS/$name.log" | tail -n 5)"
    echo "[$(date -u +%T)] !!! $name failed (exit $code), see $LOGS/$name.log"
    exit "$code"
  fi
  DONE_STEPS="$DONE_STEPS $name"
  status running "$name" 0 ""
  echo "[$(date -u +%T)] ok  $name"
}

check_env() {
  local end=$(( $(date +%s) + INSTALL_WAIT_MIN * 60 ))
  while pgrep -u "$(id -u)" -f "pretransfer/bin/python -m pip install" > /dev/null; do
    [[ $(date +%s) -ge $end ]] && { echo "pip install still running after ${INSTALL_WAIT_MIN} min"; return 1; }
    sleep 15
  done
  "$PY" -c "import paddle, paddleocr, google.genai; print('paddle', paddle.__version__, 'paddleocr', paddleocr.__version__)"
}

env_info() {
  "$PY" - > data/E1/env.json <<'EOF'
import json, sys, platform
from importlib.metadata import version
print(json.dumps({"python": sys.version.split()[0], "paddlepaddle": version("paddlepaddle"),
                  "paddleocr": version("paddleocr"), "paddlex": version("paddlex"),
                  "google-genai": version("google-genai"), "ocr_device": "cpu", "cpu": platform.processor() or "x86_64"}))
EOF
}

run check_env check_env
run ocr "$PY" -m e1.ocr_paddle --data data/E1 --device cpu
run env_info env_info
for m in $MODELS; do
  run "B_$m" "$PY" -m e1.vlm --data data/E1 --model "$m" --method B --workers "$WORKERS" --max-mean-seconds "$MAX_MEAN_SECONDS"
done
for m in $MODELS; do
  run "C_$m" "$PY" -m e1.vlm --data data/E1 --model "$m" --method C --workers "$WORKERS" --max-mean-seconds "$MAX_MEAN_SECONDS"
done
run score "$PY" -m e1.score --data data/E1 --out experiments/E1
status done score 0 ""
echo "[$(date -u +%T)] all steps done"
