#!/usr/bin/env bash
# E10 part D pair 2 on the server: serve one part A model again (scripts/e10_partA.sh stops each server when its model
# is done), same vLLM settings as part A, on 127.0.0.1:$PORT. The laptop reaches it through an ssh tunnel:
#   server:  bash scripts/e10_serve.sh qwen3-14b-awq            # detached; waits for a free GPU (never kills jobs)
#   laptop:  ssh -N -L 8000:127.0.0.1:8000 <server> &
#            LOCAL_LLM_URL=http://127.0.0.1:8000/v1 .venv/bin/python -m sim.e10_d --arms split --chat local:<model>
#   server:  bash scripts/e10_serve.sh --stop
# Log: .cache/logs/e10/serve_<model>.log, pid in .cache/logs/e10/serve.pid
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e10
PIDF=$LOGS/serve.pid
PORT=${PORT:-8000}
m=${1:?model name from e1/open_models.py, or --stop}
if [[ $m == --stop ]]; then
  [[ -f $PIDF ]] && kill "$(cat "$PIDF")" 2>/dev/null && echo "stopped $(cat "$PIDF")"
  rm -f "$PIDF"
  exit 0
fi
if [[ "${2:-}" != --fg ]]; then
  setsid nohup bash "$0" "$m" --fg > "$LOGS/serve_$m.log" 2>&1 < /dev/null &
  echo "started detached, log=$LOGS/serve_$m.log"
  exit 0
fi
export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
PY=$ROOT/.conda/pretransfer/bin/python
VPY=$ROOT/.venv-e4/bin/python
path=$("$PY" -c "from e1.open_models import MODELS, snapshot; print(snapshot(MODELS['$m']['repos'][0], download=False))")
text_only=$("$PY" -c "from e1.open_models import MODELS; print(int(MODELS['$m'].get('text_only', False)))")
while [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]; do
  echo "[$(date -u +%T)] GPU in use by another process, waiting"; sleep 120
done
mm=(); (( text_only )) || mm=(--limit-mm-per-prompt '{"image":1,"audio":0}')
echo $$ > "$PIDF"
echo "[$(date -u +%T)] serving $m from $path on 127.0.0.1:$PORT"
exec "$VPY" -m vllm.entrypoints.openai.api_server --model "$path" --served-model-name "$m" --host 127.0.0.1 \
  --port "$PORT" --max-model-len 16384 --gpu-memory-utilization 0.88 --max-num-seqs 8 "${mm[@]}"
