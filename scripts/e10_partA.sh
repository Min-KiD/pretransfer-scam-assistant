#!/usr/bin/env bash
# E10 part A on the server: larger open chat models through a vLLM OpenAI-compatible server, one at a time
# (brief: docs/tasks/E10-chat-models-and-image-flow.md).
#
#   bash scripts/e10_partA.sh --detach          # setsid + nohup; rerun any time (every step is resumable)
#
# For each model in QUEUE, once scripts/e4_part0.sh has downloaded it:
# 1. wait until nobody else uses the GPU (never kill other jobs), start the vLLM server on 127.0.0.1:$PORT
# 2. vision models only (Gemma 4): E4 modes J and Ju, `web` first with 1 request at a time (its s/image is the
#    latency number), then the other sets 8 at a time
# 3. E5: 300 sessions with this model as the assistant (thinking off, greedy, JSON schema enforced: core.llm's local
#    backend), simulated user gemini-3.5-flash-lite (paid, about 0.2 USD per model), --cap-usd 1.5
# 4. stop the server; write the model's meta (revision, licence, quant, load time, VRAM, weight size) to
#    experiments/E5/open_meta.json (+ experiments/E4/open_meta.json for vision models); weights are kept
# 5. E6 second opinion: C0 predictions on every model's sessions (CPU), E6 report, E5 report
# Progress: .cache/logs/e10/partA.log, .cache/logs/e10/partA_status.json, per model .cache/logs/e10/<m>.*.log
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e10
mkdir -p "$LOGS"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" > "$LOGS/partA.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/partA.log"
  exit 0
fi
exec 8> "$LOGS/partA.lock"
flock -n 8 || { echo "another e10_partA.sh is running"; exit 1; }

export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
PY=$ROOT/.conda/pretransfer/bin/python          # huggingface_hub (snapshot paths)
VPY=$ROOT/.venv-e4/bin/python                   # vllm, e1.e4_run, sim.e5, e6
QUEUE=${QUEUE:-"qwen3-14b-awq qwen3-8b-fp8 gemma-4-e4b-qat"}
SETS=${SETS:-E1,E1b,gen,gen_ref,web}
E4_MODES=${E4_MODES:-"J Ju"}
PORT=${PORT:-8000}
STATUS=$LOGS/partA_status.json
P0=$ROOT/.cache/logs/e4/part0_status.json       # downloads (scripts/e4_part0.sh)
[[ -f $STATUS ]] || echo '{}' > "$STATUS"

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
gpu_busy() { [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]; }

for m in $QUEUE; do
  [[ "$(state_of "$STATUS" "$m")" == done ]] && { echo "$m already done"; continue; }
  while [[ "$(state_of "$P0" "$m")" != done ]]; do
    [[ "$(state_of "$P0" "$m")" == failed ]] && break
    status "$m" waiting "download: $(state_of "$P0" "$m")"
    sleep 300
  done
  [[ "$(state_of "$P0" "$m")" == failed ]] && { status "$m" failed "download failed"; continue; }
  path=$("$PY" -c "from e1.open_models import MODELS, snapshot; print(snapshot(MODELS['$m']['repos'][0], download=False))")
  text_only=$("$PY" -c "from e1.open_models import MODELS; print(int(MODELS['$m'].get('text_only', False)))")
  while gpu_busy; do status "$m" waiting "GPU in use by another process"; sleep 300; done
  # Gemma 4 E4B also takes audio: no audio in any prompt here, so none is reserved
  mm=(); (( text_only )) || mm=(--limit-mm-per-prompt '{"image":1,"audio":0}')
  status "$m" running "vllm serve"
  t0=$(date +%s)
  "$VPY" -m vllm.entrypoints.openai.api_server --model "$path" --served-model-name "$m" --host 127.0.0.1 --port "$PORT" \
    --max-model-len 16384 --gpu-memory-utilization 0.88 --max-num-seqs 8 "${mm[@]}" > "$LOGS/$m.vllm.log" 2>&1 &
  VPID=$!
  ok=0
  for _ in $(seq 1 120); do
    curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && { ok=1; break; }
    kill -0 "$VPID" 2>/dev/null || break
    sleep 10
  done
  if (( ! ok )); then
    kill "$VPID" 2>/dev/null; wait "$VPID" 2>/dev/null
    # brief: if vLLM cannot load a model, record the error and report; no third-party build instead
    status "$m" failed "vllm did not start: $(grep -i -E 'error|exception' "$LOGS/$m.vllm.log" | tail -n 3 | tr '\n' ' ')"
    continue
  fi
  load_s=$(( $(date +%s) - t0 ))
  ( peak=0; while kill -0 "$VPID" 2>/dev/null; do
      v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); (( v > peak )) && peak=$v
      echo "$peak" > "$LOGS/$m.vram_peak"; sleep 5; done ) &
  export LOCAL_LLM_URL="http://127.0.0.1:$PORT/v1"
  if (( ! text_only )); then
    OTHER=$(tr , '\n' <<< "$SETS" | grep -vx web | paste -sd,)
    for mode in $E4_MODES; do
      status "$m" running "E4 mode $mode"
      { [[ ",$SETS," != *,web,* ]] ||
          "$VPY" -m e1.e4_run --model "local:$m" --mode "$mode" --sets web --workers 1
        [[ -z $OTHER ]] || "$VPY" -m e1.e4_run --model "local:$m" --mode "$mode" --sets "$OTHER" --workers 8
      } > "$LOGS/$m.$mode.log" 2>&1
    done
  fi
  status "$m" running "E5 sessions"
  "$VPY" -m sim.e5 --models "local:$m" --workers 8 --cap-usd 1.5 > "$LOGS/$m.e5.log" 2>&1
  kill "$VPID"; wait "$VPID" 2>/dev/null
  "$VPY" - "$m" "$load_s" "$path" "$LOGS" "$text_only" <<'EOF'
import json, re, sys
from pathlib import Path
m, load_s, path, logs, text_only = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5] == "1"
log = (logs / f"{m}.vllm.log").read_text(errors="replace")
w = re.findall(r"Model loading took ([\d.]+) GiB", log)
kv = re.findall(r"Available KV cache memory: ([\d.]+) GiB", log)
readme = path / "README.md"
lic = re.search(r"^license:\s*(\S+)", readme.read_text(errors="replace"), re.M) if readme.exists() else None
import vllm, torch, transformers
from e1.open_models import MODELS
size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())  # resolves the snapshot symlinks to blobs
meta = {"repo": MODELS[m]["repos"][0], "revision": path.name, "licence": lic.group(1) if lic else None,
        "quant": MODELS[m].get("quant", "bf16"), "weights_gb_disk": round(size / 1e9, 2),
        "server_start_s": load_s, "weights_gib_vllm": float(w[-1]) if w else None,
        "kv_cache_gib": float(kv[-1]) if kv else None,
        "vram_peak_mib": int((logs / f"{m}.vram_peak").read_text().strip() or 0),
        "gpu_memory_utilization": 0.88, "versions": f"vllm {vllm.__version__}, torch {torch.__version__}, "
                                                    f"transformers {transformers.__version__}"}
for d in ["experiments/E5"] + ([] if text_only else ["experiments/E4"]):
    p = Path(d) / "open_meta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    allm = json.loads(p.read_text()) if p.exists() else {}
    allm[f"local:{m}"] = meta
    p.write_text(json.dumps(allm, indent=1))
print(json.dumps(meta))
EOF
  status "$m" running "E6 C0 + reports"
  { "$VPY" -m e6.classify predict --model c0 --device cpu && "$VPY" -m e6.report && "$VPY" -m sim.e5 --report-only
  } > "$LOGS/$m.reports.log" 2>&1 || echo "reports failed for $m (see $LOGS/$m.reports.log)"
  summary=$(grep -h -E '^\{|^local:' "$LOGS/$m".{J,Ju}.log "$LOGS/$m.e5.log" 2>/dev/null | tail -n 4 | tr '\n' ' ')
  status "$m" done "weights kept; $summary"
done
status partA done "hf cache $(du -sh "$HF_HOME" | cut -f1), free $(df -h --output=avail "$ROOT" | tail -1)"
