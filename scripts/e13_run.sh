#!/usr/bin/env bash
# E13 on the server: one LoRA run on bf16 Qwen3-4B-Instruct-2507 (part B), then that adapter as the chat model on
# test set v2 (part C). Brief: docs/tasks/E13-chat-lora-qwen3-4b.md; plan of 2026-11-26 (planner): one run at a time,
# each started on the planner's word.
#
#   RUN=runA RANK=16 EPOCHS=1 bash scripts/e13_run.sh --detach      # setsid + nohup
#   STAGE=C RUN=runA bash scripts/e13_run.sh --detach                # part C only (adapter already trained)
#
# Gradient checkpointing stays on: without it the first example ran out of memory (16 GB card, 2026-11-26 test).
# Stops (never waits, never kills): the card used by another process when a step starts, out of memory, a row longer
# than the maximum length. Progress: .cache/logs/e13/run_$RUN.log; adapter in .cache/e13/lora/$RUN/epoch-<k>; sessions
# in experiments/E13/sessions.jsonl as model local:qwen3-4b-e13-$RUN.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e13
RUN=${RUN:?RUN name, e.g. runA}
RANK=${RANK:-16}
EPOCHS=${EPOCHS:-1}
STAGE=${STAGE:-BC}
mkdir -p "$LOGS"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup env RUN="$RUN" RANK="$RANK" EPOCHS="$EPOCHS" STAGE="$STAGE" bash "$0" > "$LOGS/run_$RUN.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/run_$RUN.log"
  exit 0
fi
exec 8> "$LOGS/run.lock"
flock -n 8 || { echo "another e13_run.sh is running"; exit 1; }

export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf XDG_CACHE_HOME=$ROOT/.cache/xdg TMPDIR=$ROOT/.cache/tmp \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1 \
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
VPY=$ROOT/.venv-e4/bin/python
BASE=Qwen/Qwen3-4B-Instruct-2507
OUT=$ROOT/.cache/e13/lora/$RUN
MODEL=qwen3-4b-e13-$RUN
PORT=${PORT:-8000}
say() { echo "[$(date -u +%T)] $*"; }
gpu_busy() { [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]; }

if [[ $STAGE == *B* ]]; then
  gpu_busy && { say "STOPPED: GPU in use by another process"; nvidia-smi --query-compute-apps=pid,used_memory --format=csv; exit 1; }
  say "train $RUN: rank $RANK, $EPOCHS epoch(s), gradient checkpointing on"
  # longest row 3,743 tokens with the model's tokenizer (check, 2026-11-26): 4096 fits every row, no truncation
  "$VPY" -m e1.chat_lora train --base "$BASE" --rank "$RANK" --epochs "$EPOCHS" --out "$OUT" --max-len 4096 \
    --gate-steps 0 > "$LOGS/train_$RUN.log" 2>&1
  rc=$?
  if (( rc != 0 )); then
    say "train $RUN FAILED rc=$rc: $(grep -h -i -E 'out of memory|error|STOPPED' "$LOGS/train_$RUN.log" | tail -n 3 | tr '\n' ' ')"
    exit 1
  fi
  say "part B done: $(grep -h '^DONE' "$LOGS/train_$RUN.log")"
fi

if [[ $STAGE == *C* ]]; then
  path=$("$VPY" -c "from e1.open_models import snapshot; print(snapshot('$BASE', download=False))")
  e=$("$VPY" -c "import json; print(json.load(open('$OUT/meta.json'))['best_epoch_by_val_loss'])")
  say "$RUN: chosen epoch $e"
  gpu_busy && { say "STOPPED: GPU in use by another process before part C"; exit 1; }
  t0=$(date +%s)
  "$VPY" -m vllm.entrypoints.openai.api_server --model "$path" --served-model-name qwen3-4b-instruct-2507 \
    --host 127.0.0.1 --port "$PORT" --max-model-len 16384 --gpu-memory-utilization 0.88 --max-num-seqs 8 \
    --enable-lora --max-lora-rank "$RANK" --max-loras 1 --lora-modules "$MODEL=$OUT/epoch-$e" > "$LOGS/vllm_$RUN.log" 2>&1 &
  VPID=$!
  ok=0
  for _ in $(seq 1 120); do
    curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && { ok=1; break; }
    kill -0 "$VPID" 2>/dev/null || break
    sleep 10
  done
  if (( ! ok )); then
    kill "$VPID" 2>/dev/null; wait "$VPID" 2>/dev/null
    say "vLLM did not start: $(grep -i -E 'error|exception' "$LOGS/vllm_$RUN.log" | tail -n 3 | tr '\n' ' ')"; exit 1
  fi
  say "vLLM up in $(( $(date +%s) - t0 ))s"
  ( peak=0; while kill -0 "$VPID" 2>/dev/null; do
      v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); (( v > peak )) && peak=$v
      echo "$peak" > "$LOGS/vram_peak_$RUN"; sleep 5; done ) &
  export LOCAL_LLM_URL="http://127.0.0.1:$PORT/v1"
  say "part C $RUN"
  "$VPY" -m sim.e5 --models "local:$MODEL" --cases sim/cases_v2 --out experiments/E13 \
    --order-seed 20261128 --full --workers 8 --cap-usd 0.35 --project-after 50 > "$LOGS/e5_$RUN.log" 2>&1
  say "sim.e5 $RUN exit $?: $(grep -E 'PROJECTION|STOPPED|n=' "$LOGS/e5_$RUN.log" | tr '\n' ' ')"
  kill "$VPID"; wait "$VPID" 2>/dev/null
  "$VPY" - "$OUT" "$LOGS" "$RUN" "$e" <<'EOF'
import json, sys
from pathlib import Path
out, logs, run, epoch = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
p = Path("experiments/E13/meta.json")
allm = json.loads(p.read_text()) if p.exists() else {"runs": {}}
m = json.loads((out / "meta.json").read_text())
m["serving"] = {"vram_peak_mib": int((logs / f"vram_peak_{run}").read_text().strip() or 0), "epoch": epoch,
                "adapter_path": str(out / f"epoch-{epoch}")}
allm["runs"][run] = m
p.write_text(json.dumps(allm, indent=1, ensure_ascii=False))
EOF
  say "part C done"
fi
say "done; adapter $(du -sh "$OUT" | cut -f1), hf cache $(du -sh "$HF_HOME" | cut -f1), free $(df -h --output=avail "$ROOT" | tail -1)"
