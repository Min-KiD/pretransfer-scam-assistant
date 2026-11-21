#!/usr/bin/env bash
# E4 part 0 on the server: the vLLM/training env and the open-model weights, in the background.
#
#   bash scripts/e4_part0.sh --detach      # setsid + nohup, survives SSH drops; rerun any time (resumes)
#
# env      : .venv-e4 (python from .conda/pretransfer) with vllm, peft, bitsandbytes. Nothing goes into ~/vidoc-dev.
# downloads: one model at a time in QUEUE order, resumable (huggingface_hub keeps partial files), retried.
#            The disk has ~40 GB free and is shared, so a model only starts when free space minus its size stays
#            >= MIN_FREE_GB; otherwise it waits (the E4 runner deletes weights it is done with).
# Progress: .cache/logs/e4/part0.log and .cache/logs/e4/part0_status.json
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e4
mkdir -p "$LOGS"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" > "$LOGS/part0.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/part0.log"
  exit 0
fi
exec 9> "$LOGS/part0.lock"
flock -n 9 || { echo "another e4_part0.sh is running"; exit 1; }

export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
mkdir -p "$HOME" "$HF_HOME" "$XDG_CACHE_HOME" "$TMPDIR"
PY=$ROOT/.conda/pretransfer/bin/python   # has huggingface_hub 2.4 + hf_xet
QUEUE=${QUEUE:-"qwen3-vl-4b qwen3.5-4b qwen3-vl-2b qwen3-vl-8b-fp8 gemma-4-e4b qwen3.5-9b"}
MIN_FREE_GB=${MIN_FREE_GB:-8}
# GB (decimal), safetensors totals from the HF API, 2026-11-22
declare -A SIZE=([qwen3-vl-2b]=4.26 [qwen3-vl-4b]=8.88 [qwen3-vl-8b-fp8]=10.59 [gemma-4-e4b]=15.99
                 [qwen3.5-4b]=9.32 [qwen3.5-9b]=19.31)
STATUS=$LOGS/part0_status.json
[[ -f $STATUS ]] || echo '{}' > "$STATUS"

status() {  # key state detail
  python3 - "$STATUS" "$1" "$2" "$3" <<'EOF'
import json, sys, datetime
p, k, st, d = sys.argv[1:]
s = json.load(open(p))
s[k] = {"state": st, "detail": d, "t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump(s, open(p + ".tmp", "w"), indent=1)
__import__("os").replace(p + ".tmp", p)
EOF
  echo "[$(date -u +%T)] $1: $2 $3"
}
free_gb() { df -k --output=avail "$ROOT" | tail -1 | awk '{printf "%.1f", $1/1e6}'; }
done_already() { python3 -c "import json,sys; print(json.load(open('$STATUS')).get('$1',{}).get('state',''))"; }

# ---------------------------------------------------------------- env (parallel with the downloads)
(
  if [[ "$(done_already env)" == done ]]; then exit 0; fi
  status env running "venv + pip install"
  [[ -x .venv-e4/bin/python ]] || "$PY" -m venv .venv-e4
  .venv-e4/bin/pip install -q -U pip > "$LOGS/env.log" 2>&1
  if .venv-e4/bin/pip install "vllm==0.34.0" "peft==0.22.0" "bitsandbytes==0.50.2" "qwen-vl-utils==0.0.14" \
       "google-genai" "pillow" >> "$LOGS/env.log" 2>&1; then
    status env done "$(.venv-e4/bin/python -c 'import torch,transformers,vllm,peft;print("torch",torch.__version__,"transformers",transformers.__version__,"vllm",vllm.__version__,"peft",peft.__version__)' 2>&1 | tail -1); $(du -sh .venv-e4 | cut -f1)"
  else
    status env failed "$(tail -n 3 "$LOGS/env.log" | tr '\n' ' ')"
  fi
) &
ENV_PID=$!

# ---------------------------------------------------------------- downloads
for m in $QUEUE; do
  [[ "$(done_already "$m")" == done ]] && { echo "$m already downloaded"; continue; }
  need=${SIZE[$m]}
  while python3 -c "import sys; sys.exit(0 if $(free_gb) - $need < $MIN_FREE_GB else 1)"; do
    status "$m" waiting "free $(free_gb) GB, needs $need GB + $MIN_FREE_GB GB margin"
    sleep 300
  done
  status "$m" running "download $need GB (free $(free_gb) GB)"
  t0=$(date +%s); ok=0
  for attempt in 1 2 3 4 5 6; do
    if "$PY" -m e1.open_models download --model "$m" >> "$LOGS/$m.download.log" 2>&1; then ok=1; break; fi
    sleep 60
  done
  dt=$(( $(date +%s) - t0 ))
  if (( ok )); then
    status "$m" done "$(tail -n 1 "$LOGS/$m.download.log"); $(python3 -c "print(round($need*1000/max($dt,1),2))") MB/s"
  else
    status "$m" failed "$(tail -n 2 "$LOGS/$m.download.log" | tr '\n' ' ')"
  fi
done
wait "$ENV_PID"
status part0 done "free $(free_gb) GB, hf cache $(du -sh "$HF_HOME" | cut -f1)"
