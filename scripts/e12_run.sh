#!/usr/bin/env bash
# E12 on the server: untrained Qwen3-4B-Instruct-2507 as the chat model on test set v2
# (brief: docs/tasks/E12-chat-qwen3-4b-untrained.md).
#
#   bash scripts/e12_run.sh --detach            # setsid + nohup; rerun any time (sim.e5 skips finished sessions)
#
# 1. disk check (stop under 12 GB free), download the weights once (never restarted while running)
# 2. wait until nobody else uses the GPU (never kill other jobs), vLLM on 127.0.0.1:$PORT, same settings as E10 part A
#    (context 16384 >= the brief's 8192, greedy, thinking off, JSON schema enforced: core.llm's local backend)
# 3. sim.e5 on sim/cases_v2 with the T6 part C order seed, simulated user gemini-3.5-flash-lite (VICTIM_PROMPT_VIEC),
#    --cap-usd 0.35 --project-after 50 -> experiments/E12/sessions.jsonl
# 4. stop the server (weights kept), meta (revision, licence, load time, peak VRAM, weight size) -> experiments/E12/meta.json
# Progress: .cache/logs/e12/run.log; per step .cache/logs/e12/*.log
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e12
mkdir -p "$LOGS"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" > "$LOGS/run.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/run.log"
  exit 0
fi
exec 8> "$LOGS/run.lock"
flock -n 8 || { echo "another e12_run.sh is running"; exit 1; }

export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
PY=$ROOT/.conda/pretransfer/bin/python          # huggingface_hub
VPY=$ROOT/.venv-e4/bin/python                   # vllm, sim.e5
M=qwen3-4b-instruct-2507
PORT=${PORT:-8000}
say() { echo "[$(date -u +%T)] $*"; }
free_gb() { df -BG --output=avail "$ROOT" | tail -1 | tr -dc 0-9; }

path=$("$PY" -c "from e1.open_models import MODELS, snapshot; print(snapshot(MODELS['$M']['repos'][0], download=False))" 2>/dev/null)
if [[ -z $path ]]; then
  (( $(free_gb) >= 12 )) || { say "STOPPED: only $(free_gb) GB free (< 12)"; exit 1; }
  say "download (free $(free_gb) GB)"
  "$PY" -m e1.open_models download --model "$M" > "$LOGS/download.log" 2>&1 || { say "download FAILED"; tail -n 3 "$LOGS/download.log"; exit 1; }
  path=$("$PY" -c "from e1.open_models import MODELS, snapshot; print(snapshot(MODELS['$M']['repos'][0], download=False))")
fi
say "weights at $path"
while [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]; do
  say "GPU in use by another process, waiting"; sleep 120
done
t0=$(date +%s)
"$VPY" -m vllm.entrypoints.openai.api_server --model "$path" --served-model-name "$M" --host 127.0.0.1 --port "$PORT" \
  --max-model-len 16384 --gpu-memory-utilization 0.88 --max-num-seqs 8 > "$LOGS/vllm.log" 2>&1 &
VPID=$!
ok=0
for _ in $(seq 1 120); do
  curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && { ok=1; break; }
  kill -0 "$VPID" 2>/dev/null || break
  sleep 10
done
if (( ! ok )); then
  kill "$VPID" 2>/dev/null; wait "$VPID" 2>/dev/null
  say "vLLM did not start: $(grep -i -E 'error|exception' "$LOGS/vllm.log" | tail -n 3 | tr '\n' ' ')"; exit 1
fi
load_s=$(( $(date +%s) - t0 ))
say "vLLM up in ${load_s}s"
( peak=0; while kill -0 "$VPID" 2>/dev/null; do
    v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); (( v > peak )) && peak=$v
    echo "$peak" > "$LOGS/vram_peak"; sleep 5; done ) &
export LOCAL_LLM_URL="http://127.0.0.1:$PORT/v1"
say "E12 sessions"
"$VPY" -m sim.e5 --models "local:$M" --cases sim/cases_v2 --out experiments/E12 --order-seed 20261128 --full \
  --workers 8 --cap-usd 0.35 --project-after 50 > "$LOGS/e5.log" 2>&1
say "sim.e5 exit $?: $(grep -E 'PROJECTION|STOPPED|n=' "$LOGS/e5.log" | tr '\n' ' ')"
kill "$VPID"; wait "$VPID" 2>/dev/null
"$VPY" - "$M" "$load_s" "$path" "$LOGS" <<'EOF'
import json, re, sys
from pathlib import Path
m, load_s, path, logs = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
log = (logs / "vllm.log").read_text(errors="replace")
w = re.findall(r"Model loading took ([\d.]+) GiB", log)
kv = re.findall(r"Available KV cache memory: ([\d.]+) GiB", log)
readme = path / "README.md"
lic = re.search(r"^license:\s*(\S+)", readme.read_text(errors="replace"), re.M) if readme.exists() else None
import vllm, torch, transformers
from e1.open_models import MODELS
size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())  # resolves the snapshot symlinks to blobs
meta = {"model": f"local:{m}", "repo": MODELS[m]["repos"][0], "revision": path.name,
        "licence": lic.group(1) if lic else None, "quant": MODELS[m]["quant"], "weights_gb_disk": round(size / 1e9, 2),
        "server_start_s": load_s, "weights_gib_vllm": float(w[-1]) if w else None,
        "kv_cache_gib": float(kv[-1]) if kv else None, "max_model_len": 16384,
        "vram_peak_mib": int((logs / "vram_peak").read_text().strip() or 0), "gpu_memory_utilization": 0.88,
        "versions": f"vllm {vllm.__version__}, torch {torch.__version__}, transformers {transformers.__version__}"}
Path("experiments/E12/meta.json").write_text(json.dumps(meta, indent=1))
print(json.dumps(meta))
EOF
say "done; hf cache $(du -sh "$HF_HOME" | cut -f1), free $(free_gb) GB"
