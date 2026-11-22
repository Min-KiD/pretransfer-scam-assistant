#!/usr/bin/env bash
# E4 phase A (+ E5 open part) on the server: every open VLM through a vLLM OpenAI-compatible server, one at a time.
#
#   bash scripts/e4_phaseA.sh --detach          # setsid + nohup; rerun any time (runs are resumable)
#
# 0. PP-OCRv6 GPU text for images that lack it (vidoc env, read-only), needed by the regex rows and mode O.
# For each model in QUEUE, once scripts/e4_part0.sh has downloaded it:
# 1. wait until nobody else uses the GPU (never kill other jobs), start `vllm serve` on 127.0.0.1:$PORT
# 2. E4 modes J (schema constrained), Ju (schema only in the prompt), O (OCR text -> JSON), 1 request at a time so
#    s/image is real latency on the 4060 Ti; sets E1,E1b,gen,web
# 3. E5: 300 text-only sessions with this model as the assistant (victim = gemini-3.5-flash-lite, paid), 8 at a time
# 4. stop the server, write experiments/E4/open_meta.json (+ E5), delete the weights unless the model is in KEEP
#    (the disk has ~40 GB free; scripts/e4_part0.sh downloads the next model when space frees up)
# Progress: .cache/logs/e4/phaseA.log, .cache/logs/e4/phaseA_status.json, per model .cache/logs/e4/<m>.*.log
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e4
mkdir -p "$LOGS"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" > "$LOGS/phaseA.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/phaseA.log"
  exit 0
fi
exec 8> "$LOGS/phaseA.lock"
flock -n 8 || { echo "another e4_phaseA.sh is running"; exit 1; }

export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PADDLE_PDX_CACHE_HOME=$ROOT/.cache/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
PY=$ROOT/.conda/pretransfer/bin/python          # huggingface_hub (snapshot paths, clean)
HPY=${HPY:-/home/intern/vidoc-dev/.venvs/mineru/bin/python}   # PP-OCRv6 env from E1b, used read-only
QUEUE=${QUEUE:-"qwen3-vl-4b qwen3.5-4b qwen3-vl-2b qwen3-vl-8b-fp8 gemma-4-e4b qwen3.5-9b"}
SETS=${SETS:-E1,E1b,gen,web}
KEEP=${KEEP:-}
PORT=${PORT:-8000}
STATUS=$LOGS/phaseA_status.json
P0=$LOGS/part0_status.json
[[ -f $STATUS ]] || echo '{}' > "$STATUS"
declare -A QUANT=([gemma-4-e4b]="--quantization fp8" [qwen3.5-9b]="--quantization fp8")

status() {  # key state detail
  python3 - "$STATUS" "$1" "$2" "$3" <<'EOF'
import json, sys, datetime, os
p, k, st, d = sys.argv[1:]
s = json.load(open(p))
s[k] = {"state": st, "detail": d, "t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump(s, open(p + ".tmp", "w"), indent=1)
os.replace(p + ".tmp", p)
EOF
  echo "[$(date -u +%T)] $1: $2 $3"
}
state_of() { python3 -c "import json;print(json.load(open('$1')).get('$2',{}).get('state',''))" 2>/dev/null; }
gpu_busy() {  # other processes on the GPU (ours is stopped between models)
  [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]
}

# ---------------------------------------------------------------- 0. env + PP-OCRv6 text for new images
while [[ "$(state_of "$P0" env)" != done ]]; do
  [[ "$(state_of "$P0" env)" == failed ]] && { status phaseA failed "env install failed (see part0)"; exit 1; }
  sleep 120
done
while gpu_busy; do status ocr waiting "GPU in use by another process"; sleep 300; done
status ocr running "PP-OCRv6 GPU on $SETS"
PYTHONPATH=$ROOT/.cache/pylib:$ROOT "$HPY" -m e1.open_models run --model pp-ocrv6-gpu --mode T --sets "$SETS" \
  --budget-min 120 --min-images 0 > "$LOGS/ocr.log" 2>&1 && status ocr done "$(tail -n 1 "$LOGS/ocr.log")" \
  || status ocr failed "$(tail -n 2 "$LOGS/ocr.log" | tr '\n' ' ')"

# ---------------------------------------------------------------- per model
for m in $QUEUE; do
  [[ "$(state_of "$STATUS" "$m")" == done ]] && { echo "$m already done"; continue; }
  while [[ "$(state_of "$P0" "$m")" != done ]]; do
    [[ "$(state_of "$P0" "$m")" == failed ]] && break
    status "$m" waiting "download: $(state_of "$P0" "$m")"
    sleep 300
  done
  [[ "$(state_of "$P0" "$m")" == failed ]] && { status "$m" failed "download failed"; continue; }
  path=$("$PY" -c "from e1.open_models import MODELS, snapshot; print(snapshot(MODELS['$m']['repos'][0], download=False))")
  while gpu_busy; do status "$m" waiting "GPU in use by another process"; sleep 300; done
  mm=""; [[ $m == qwen* ]] && mm='--mm-processor-kwargs {"max_pixels":2097152}'
  status "$m" running "vllm serve"
  t0=$(date +%s)
  "$VPY" -m vllm.entrypoints.openai.api_server --model "$path" --served-model-name "$m" --host 127.0.0.1 --port "$PORT" \
    --max-model-len 16384 --gpu-memory-utilization 0.88 --max-num-seqs 8 --limit-mm-per-prompt '{"image":1}' \
    ${QUANT[$m]:-} $mm > "$LOGS/$m.vllm.log" 2>&1 &
  VPID=$!
  ok=0
  for _ in $(seq 1 120); do
    curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && { ok=1; break; }
    kill -0 "$VPID" 2>/dev/null || break
    sleep 10
  done
  if (( ! ok )); then
    kill "$VPID" 2>/dev/null; wait "$VPID" 2>/dev/null
    status "$m" failed "vllm did not start: $(grep -i -E 'error|exception' "$LOGS/$m.vllm.log" | tail -n 2 | tr '\n' ' ')"
    continue
  fi
  load_s=$(( $(date +%s) - t0 ))
  # VRAM of the server process, sampled every 5 s (vLLM reserves --gpu-memory-utilization up front; the weight size
  # from its log is the number that says whether the model fits)
  ( peak=0; while kill -0 "$VPID" 2>/dev/null; do
      v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); (( v > peak )) && peak=$v
      echo "$peak" > "$LOGS/$m.vram_peak"; sleep 5; done ) &
  export LOCAL_LLM_URL="http://127.0.0.1:$PORT/v1"
  for mode in J Ju O; do
    status "$m" running "E4 mode $mode"
    "$VPY" -m e1.e4_run --model "local:$m" --mode "$mode" --sets "$SETS" --workers 1 > "$LOGS/$m.$mode.log" 2>&1
  done
  status "$m" running "E5 sessions"
  "$VPY" -m sim.e5 --models "local:$m" --workers 8 --cap-usd 1.5 > "$LOGS/$m.e5.log" 2>&1
  kill "$VPID"; wait "$VPID" 2>/dev/null
  "$VPY" - "$m" "$load_s" "$path" "$LOGS" <<'EOF'
import json, re, sys
from pathlib import Path
m, load_s, path, logs = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
log = (logs / f"{m}.vllm.log").read_text(errors="replace")
w = re.findall(r"Model loading took ([\d.]+) GiB", log)
kv = re.findall(r"Available KV cache memory: ([\d.]+) GiB", log)
import vllm, torch, transformers
from e1.open_models import MODELS
meta = {"repo": MODELS[m]["repos"][0], "revision": path.name, "quant": MODELS[m].get("quant", "bf16"),
        "server_start_s": load_s, "weights_gib_vllm": float(w[-1]) if w else None,
        "kv_cache_gib": float(kv[-1]) if kv else None,
        "vram_peak_mib": int((logs / f"{m}.vram_peak").read_text().strip() or 0),
        "gpu_memory_utilization": 0.88, "versions": f"vllm {vllm.__version__}, torch {torch.__version__}, "
                                                    f"transformers {transformers.__version__}"}
for d in ("experiments/E4", "experiments/E5"):
    p = Path(d) / "open_meta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    allm = json.loads(p.read_text()) if p.exists() else {}
    allm[f"local:{m}"] = meta
    p.write_text(json.dumps(allm, indent=1))
print(json.dumps(meta))
EOF
  summary=$(grep -h '^{' "$LOGS/$m.J.log" "$LOGS/$m.Ju.log" "$LOGS/$m.O.log" 2>/dev/null | tr '\n' ' ')
  if [[ " $KEEP " == *" $m "* ]]; then
    status "$m" done "kept weights; $summary"
  else
    "$PY" -m e1.open_models clean --model "$m" --force >> "$LOGS/$m.clean.log" 2>&1
    status "$m" done "weights deleted; $summary"
  fi
done
status phaseA done "hf cache $(du -sh "$HF_HOME" | cut -f1), free $(df -h --output=avail "$ROOT" | tail -1)"
