#!/usr/bin/env bash
# E1b server pipeline. Unlike E1, a failing model is recorded and the next model runs.
#
#   bash scripts/e1b_server_run.sh --detach   # background (setsid + nohup), survives SSH drops
#
# Steps
#   gemini   : method B, gemini-3.5-flash-lite on the 100 hard images (API, in parallel with the GPU work)
#   per model: GPU check (other processes > 2 GB: wait 10 min, then skip)
#              -> download guard: disk (E1b <= 25 GB, >= 15 GB free) and time (size / measured speed <= 30 min)
#              -> download (30 min cap) -> run each mode (20 min budget, continues until >= 60 images)
#              -> delete weights
#   ocr_cpu  : PP-OCRv6 CPU on E1b, only if the GPU PP-OCRv6 run produced nothing
#
# Python for the GPU models: the existing ~/vidoc-dev/.venvs/mineru interpreter (torch 2.11 cu130,
# transformers 5.22.2), used read-only: nothing is installed into it and bytecode writing is off. Extra pure
# packages (paddleocr, paddlex and their missing deps) live in .cache/pylib inside this project.
# Progress: data/E1b/open/events.jsonl and .cache/logs/e1b/status.json; logs in .cache/logs/e1b/.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e1b
STATUS=$LOGS/status.json
EVENTS=$ROOT/data/E1b/open/events.jsonl
PY=$ROOT/.conda/pretransfer/bin/python
HPY=${HPY:-/home/intern/vidoc-dev/.venvs/mineru/bin/python}
MODELS=${MODELS:-"pp-ocrv6-gpu qwen3-vl-8b paddleocr-vl-1.6 mineru2.5-pro glm-ocr gemma-4-e4b"}
INSTALL_MIN=${INSTALL_MIN:-30}
RUN_BUDGET_MIN=${RUN_BUDGET_MIN:-20}
MIN_FREE_GB=${MIN_FREE_GB:-15}
MAX_E1B_GB=${MAX_E1B_GB:-25}
DL_MBPS=${DL_MBPS:-2.0}   # measured on 2026-11-20 (curl, 1 and 8 connections); updated after each download
mkdir -p "$LOGS" "$(dirname "$EVENTS")"

if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" > "$LOGS/pipeline.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/pipeline.log status=$STATUS"
  exit 0
fi
exec 9> "$LOGS/pipeline.lock"
flock -n 9 || { echo "another e1b_server_run.sh is running"; exit 1; }

# Every cache stays inside the project (paddle and HF would otherwise write under the real $HOME).
export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PADDLE_PDX_CACHE_HOME=$ROOT/.cache/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
mkdir -p "$HOME" "$HF_HOME" "$XDG_CACHE_HOME" "$TMPDIR"
STARTED=$(date -u +%FT%TZ)
hpy() { PYTHONPATH=$ROOT/.cache/pylib:$ROOT "$HPY" "$@"; }

# Download sizes (GB, decimal) from the HF API tree listing, 2026-11-20.
declare -A SIZE=([pp-ocrv6-gpu]=0.14 [qwen3-vl-8b]=17.53 [qwen3-vl-4b]=8.88 [paddleocr-vl-1.6]=1.92
                 [mineru2.5-pro]=2.31 [glm-ocr]=2.65 [gemma-4-e4b]=15.99)
declare -A MODES=([pp-ocrv6-gpu]="T" [qwen3-vl-8b]="J" [qwen3-vl-4b]="J" [paddleocr-vl-1.6]="T"
                  [mineru2.5-pro]="T" [glm-ocr]="T J" [gemma-4-e4b]="J")

event() {  # model state reason
  python3 -c 'import json,sys,datetime; print(json.dumps({"t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "model": sys.argv[1], "state": sys.argv[2], "reason": sys.argv[3]}, ensure_ascii=False))' \
    "$1" "$2" "$3" >> "$EVENTS"
  echo "[$(date -u +%T)] $1: $2 ${3:0:200}"
  STARTED="$STARTED" STATE="${PIPE_STATE:-running}" python3 - "$EVENTS" "$STATUS" <<'EOF'
import json, os, sys, datetime
models = {}
for l in open(sys.argv[1], encoding="utf-8"):
    e = json.loads(l)
    m = models.setdefault(e["model"], {})
    m.setdefault("started", e["t"])
    m.update(state=e["state"], reason=e["reason"] or m.get("reason"), updated=e["t"])
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
s = {"state": os.environ["STATE"], "pipeline_started": os.environ["STARTED"], "updated": now, "models": models}
json.dump(s, open(sys.argv[2] + ".tmp", "w"), indent=1, ensure_ascii=False)
os.replace(sys.argv[2] + ".tmp", sys.argv[2])
EOF
}

lastlines() { grep -v -i -E "warn|it/s\]|%\|" "$1" | tail -n 3 | tr '\n' ' '; }

gpu_busy_mib() {  # GPU memory held by processes that are not ours
  local mine; mine=$(pgrep -u "$(id -u)" -d, -f "[e]1.open_models" || true)
  nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null |
    awk -F', ' -v mine=",$mine," 'index(mine, ","$1",")==0 {s+=$2} END {print s+0}'
}
e1b_gb() { du -sk "$HF_HOME" "$ROOT/.cache/pylib" "$ROOT/.cache/paddlex" 2>/dev/null | awk '{s+=$1} END {printf "%.1f", s/1e6}'; }
free_gb() { df -k --output=avail "$ROOT" | tail -1 | awk '{printf "%.1f", $1/1e6}'; }

# ---------------------------------------------------------------- Gemini reference (API, parallel)
event gemini-3.5-flash-lite running "B on E1b"
( "$PY" -m e1.vlm --data data/E1b --model gemini-3.5-flash-lite --method B --workers 6 --max-mean-seconds 60 \
    > "$LOGS/gemini.log" 2>&1 && event gemini-3.5-flash-lite done "" \
    || event gemini-3.5-flash-lite failed "$(lastlines "$LOGS/gemini.log")" ) &
GEM_PID=$!

event env done "$(hpy -c 'import torch,transformers;print("python", __import__("sys").version.split()[0], "torch",torch.__version__,"transformers",transformers.__version__, "gpu", torch.cuda.get_device_name(0))' 2>&1 | tail -1)"

# ---------------------------------------------------------------- models
for m in $MODELS; do
  event "$m" running "gpu check"
  busy=$(gpu_busy_mib)
  if (( busy > 2048 )); then
    event "$m" running "GPU busy (${busy} MiB by other processes), waiting 10 min"
    sleep 600; busy=$(gpu_busy_mib)
    if (( busy > 2048 )); then event "$m" skipped "GPU busy: ${busy} MiB held by other processes after 10 min"; continue; fi
  fi
  need=${SIZE[$m]}
  guard=$(python3 -c "
f,u,n,s,cap,mf,mx=map(float,'$(free_gb) $(e1b_gb) $need $DL_MBPS $INSTALL_MIN $MIN_FREE_GB $MAX_E1B_GB'.split())
eta=n*1000/s/60
if f-n<mf or u+n>mx: print(f'disk guard: free {f} GB, E1b uses {u} GB, model needs {n} GB')
elif eta>cap: print(f'download {n} GB at the measured {s:.1f} MB/s needs about {eta:.0f} min, over the {cap:.0f} min install cap')
")
  if [[ -n "$guard" ]]; then event "$m" skipped "$guard"; continue; fi
  event "$m" running "download ${need} GB"
  t0=$(date +%s)
  timeout $(( INSTALL_MIN * 60 )) bash -c "$(declare -f hpy); ROOT=$ROOT HPY=$HPY hpy -m e1.open_models download --model $m" \
    > "$LOGS/$m.download.log" 2>&1
  code=$?
  if [[ $code -ne 0 ]]; then
    reason=$([[ $code -eq 124 ]] && echo "download not finished after ${INSTALL_MIN} min" || lastlines "$LOGS/$m.download.log")
    hpy -m e1.open_models clean --model "$m" >> "$LOGS/$m.download.log" 2>&1
    event "$m" skipped "$reason"; continue
  fi
  dt=$(( $(date +%s) - t0 ))
  (( dt > 30 )) && DL_MBPS=$(python3 -c "print(round(max(0.5, $need*1000/$dt), 2))")
  ok=1
  for mode in ${MODES[$m]}; do
    event "$m" running "run $mode"
    timeout $(( (RUN_BUDGET_MIN + 25) * 60 )) env PYTHONPATH="$ROOT/.cache/pylib:$ROOT" "$HPY" -m e1.open_models run \
      --model "$m" --mode "$mode" --budget-min "$RUN_BUDGET_MIN" --min-images 60 > "$LOGS/$m.$mode.log" 2>&1
    code=$?
    [[ $code -ne 0 ]] && { ok=0; event "$m" failed "run $mode exit $code: $(lastlines "$LOGS/$m.$mode.log")"; }
  done
  # keep the weights of a failed run so a fixed rerun needs no new download (the disk guard still applies)
  [[ $ok -eq 1 ]] && hpy -m e1.open_models clean --model "$m" >> "$LOGS/$m.download.log" 2>&1
  [[ $ok -eq 1 ]] && event "$m" done "downloaded in ${dt}s; $(tail -n 1 "$LOGS/$m.${MODES[$m]##* }.log")"
done

# ---------------------------------------------------------------- PP-OCRv6 CPU fallback for method A on E1b
if ! ls data/E1b/runs/T__pp-ocrv6-gpu/*.json > /dev/null 2>&1; then
  event pp-ocrv6-cpu running "A on E1b (CPU), the GPU run produced nothing"
  "$PY" -m e1.ocr_paddle --data data/E1b --device cpu > "$LOGS/ocr_cpu.log" 2>&1 \
    && event pp-ocrv6-cpu done "" || event pp-ocrv6-cpu failed "$(lastlines "$LOGS/ocr_cpu.log")"
fi

wait "$GEM_PID"
PIPE_STATE=done event pipeline done "free $(free_gb) GB, E1b caches $(e1b_gb) GB"
