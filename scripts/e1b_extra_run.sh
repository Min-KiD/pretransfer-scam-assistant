#!/usr/bin/env bash
# E1b part 1b: run the reference and every open model that finished the main pipeline on the extra sets.
#
#   SETS=gen bash scripts/e1b_extra_run.sh --detach            # gen set now
#   SETS=web FINAL=1 bash scripts/e1b_extra_run.sh --detach    # web set later, then delete the open-model weights
#
# Waits for the main pipeline (same lock file), so the GPU still runs one model at a time. Models: those whose
# last event in data/E1b/open/events.jsonl is "done". gemini-3.5-flash-lite (method B) runs on each set first.
# Outputs go to RUN_DIRS in e1/vlm.py (gen: data/E1b/gen/runs, web: data/E1b/web_runs); nothing is written
# into data/E1b/real. Progress: data/E1b/open/events_extra.jsonl, .cache/logs/e1b/extra_status.json.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e1b
STATUS=$LOGS/extra_status.json
EVENTS=$ROOT/data/E1b/open/events_extra.jsonl
PY=$ROOT/.conda/pretransfer/bin/python
HPY=${HPY:-/home/intern/vidoc-dev/.venvs/mineru/bin/python}
SETS=${SETS:-gen}
FINAL=${FINAL:-0}
RUN_BUDGET_MIN=${RUN_BUDGET_MIN:-20}
mkdir -p "$LOGS"

if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup env SETS="$SETS" FINAL="$FINAL" bash "$0" > "$LOGS/extra.${SETS//,/-}.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/extra.${SETS//,/-}.log status=$STATUS"
  exit 0
fi

export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PADDLE_PDX_CACHE_HOME=$ROOT/.cache/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
mkdir -p "$HOME" "$HF_HOME" "$XDG_CACHE_HOME" "$TMPDIR"
hpy() { PYTHONPATH=$ROOT/.cache/pylib:$ROOT "$HPY" "$@"; }
declare -A MODES=([pp-ocrv6-gpu]="T" [qwen3-vl-8b]="J" [qwen3-vl-4b]="J" [paddleocr-vl-1.6]="T"
                  [mineru2.5-pro]="T" [glm-ocr]="T J" [gemma-4-e4b]="J")

event() {  # model state reason
  python3 - "$EVENTS" "$STATUS" "$1" "$2" "$3" "$SETS" <<'EOF'
import datetime, json, os, sys
events, status, model, state, reason, sets = sys.argv[1:]
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(events, "a", encoding="utf-8") as f:
    f.write(json.dumps({"t": now, "sets": sets, "model": model, "state": state, "reason": reason}, ensure_ascii=False) + "\n")
s = json.load(open(status)) if os.path.exists(status) else {}
s.setdefault(sets, {})[model] = {"state": state, "reason": reason, "updated": now}
json.dump(s, open(status + ".tmp", "w"), indent=1, ensure_ascii=False)
os.replace(status + ".tmp", status)
print(f"[{now[11:19]}] {sets} {model}: {state} {reason[:200]}", flush=True)
EOF
}
lastlines() { grep -v -i -E "warn|it/s\]|%\|" "$1" | tail -n 3 | tr '\n' ' '; }
gpu_busy_mib() {
  local mine; mine=$(pgrep -u "$(id -u)" -d, -f "[e]1.open_models" || true)
  nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null |
    awk -F', ' -v mine=",$mine," 'index(mine, ","$1",")==0 {s+=$2} END {print s+0}'
}

for s in ${SETS//,/ }; do
  event gemini-3.5-flash-lite running "B on $s"
  "$PY" -m e1.vlm --set "$s" --model gemini-3.5-flash-lite --method B --workers 6 > "$LOGS/extra.gemini.$s.log" 2>&1 \
    && event gemini-3.5-flash-lite done "B on $s" \
    || event gemini-3.5-flash-lite failed "$(lastlines "$LOGS/extra.gemini.$s.log")"
done

exec 9> "$LOGS/pipeline.lock"
event gpu-lock running "waiting for the main GPU pipeline to finish"
flock 9
event gpu-lock done ""

DONE_MODELS=$(python3 -c '
import json, sys
last = {}
for l in open(sys.argv[1], encoding="utf-8"):
    e = json.loads(l); last[e["model"]] = e["state"]
print(" ".join(m for m, st in last.items() if st == "done" and m not in ("env", "pipeline", "gemini-3.5-flash-lite", "pp-ocrv6-cpu")))
' "$ROOT/data/E1b/open/events.jsonl")
event plan done "models: $DONE_MODELS"

for m in $DONE_MODELS; do
  busy=$(gpu_busy_mib)
  if (( busy > 2048 )); then
    event "$m" running "GPU busy (${busy} MiB by other processes), waiting 10 min"
    sleep 600; busy=$(gpu_busy_mib)
    if (( busy > 2048 )); then event "$m" skipped "GPU busy: ${busy} MiB after 10 min"; continue; fi
  fi
  for mode in ${MODES[$m]}; do
    event "$m" running "run $mode on $SETS"
    timeout $(( (RUN_BUDGET_MIN + 25) * 60 )) env PYTHONPATH="$ROOT/.cache/pylib:$ROOT" "$HPY" -m e1.open_models run \
      --model "$m" --mode "$mode" --sets "$SETS" --budget-min "$RUN_BUDGET_MIN" --min-images 0 \
      > "$LOGS/extra.$m.$mode.${SETS//,/-}.log" 2>&1 \
      && event "$m" done "$mode on $SETS: $(tail -n 1 "$LOGS/extra.$m.$mode.${SETS//,/-}.log")" \
      || event "$m" failed "$mode on $SETS exit $?: $(lastlines "$LOGS/extra.$m.$mode.${SETS//,/-}.log")"
  done
done

if [[ "$FINAL" == "1" ]]; then
  for m in $DONE_MODELS; do hpy -m e1.open_models clean --model "$m" --force >> "$LOGS/extra.clean.log" 2>&1; done
  event weights done "deleted open-model weights: $(du -sh "$HF_HOME" 2>/dev/null | cut -f1) left in .cache/hf"
fi
event pipeline done "free $(df -h --output=avail "$ROOT" | tail -1 | tr -d ' ')"
