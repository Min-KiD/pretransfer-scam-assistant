#!/usr/bin/env bash
# E13 on the server: one LoRA run on bf16 Qwen3-4B-Instruct-2507 (part B), that run's lowest-val-loss epoch as the
# chat model on test set v2 (part C), and the teacher-forced ask/stop check on the val file (T). Brief:
# docs/tasks/E13-chat-lora-qwen3-4b.md; one run at a time, each started on the planner's word.
#
#   RUN=runB TRAIN=data/T5/opus/train_final.jsonl VAL=data/T5/opus/val_all.jsonl STAGE=BC bash scripts/e13_run.sh --detach
#   RUN=runC EPOCHS=3 TRAIN=data/T5/opus/train_final2.jsonl VAL=data/T5/opus/val_all.jsonl TF_ALSO=runB \
#     bash scripts/e13_run.sh --detach                                  # B, C, then T on runC epochs 1-3 + runB
#   STAGE=C RUN=runC bash scripts/e13_run.sh --detach                    # part C only (adapter already trained)
#
# Gradient checkpointing stays on: without it the first example ran out of memory (16 GB card, 2026-11-26 test).
# Stops (never waits, never kills): the card used by another process when a stage starts, out of memory, a row longer
# than the maximum length. Progress: .cache/logs/e13/run_$RUN.log; adapters in .cache/e13/lora/$RUN/epoch-<k> (nothing
# is deleted); sessions in experiments/E13/sessions.jsonl as model local:qwen3-4b-e13-$RUN; the teacher-forced check
# in experiments/E13/tf.jsonl as models local:qwen3-4b-e13-<run>-e<k>.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e13
RUN=${RUN:?RUN name, e.g. runC}
RANK=${RANK:-16}
EPOCHS=${EPOCHS:-1}
STAGE=${STAGE:-BCT}
TRAIN=${TRAIN:-data/T5/opus/train_final.jsonl}
VAL=${VAL:-data/T5/opus/val_all.jsonl}
TF_ALSO=${TF_ALSO:-}   # earlier runs whose every epoch adapter joins the teacher-forced check, space-separated
mkdir -p "$LOGS"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup env RUN="$RUN" RANK="$RANK" EPOCHS="$EPOCHS" STAGE="$STAGE" TRAIN="$TRAIN" VAL="$VAL" \
    TF_ALSO="$TF_ALSO" bash "$0" > "$LOGS/run_$RUN.log" 2>&1 < /dev/null &
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
LORA=$ROOT/.cache/e13/lora
OUT=$LORA/$RUN
MODEL=qwen3-4b-e13-$RUN
PORT=${PORT:-8000}
VPID=
say() { echo "[$(date -u +%T)] $*"; }
gpu_busy() { [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]; }
trap '[[ -n "$VPID" ]] && kill "$VPID" 2>/dev/null' EXIT

# serve <log tag> <max loras> name=dir ...: the bf16 base in vLLM with these adapters (same settings as E12 and
# Part C of Run B); sets VPID and records the whole card's peak VRAM in $LOGS/vram_peak_<tag>.
serve() {
  local tag=$1 nl=$2; shift 2
  local path t0 ok=0
  path=$("$VPY" -c "from e1.open_models import snapshot; print(snapshot('$BASE', download=False))")
  gpu_busy && { say "STOPPED: GPU in use by another process before $tag"; exit 1; }
  t0=$(date +%s)
  "$VPY" -m vllm.entrypoints.openai.api_server --model "$path" --served-model-name qwen3-4b-instruct-2507 \
    --host 127.0.0.1 --port "$PORT" --max-model-len 16384 --gpu-memory-utilization 0.88 --max-num-seqs 8 \
    --enable-lora --max-lora-rank "$RANK" --max-loras "$nl" --lora-modules "$@" > "$LOGS/vllm_$tag.log" 2>&1 &
  VPID=$!
  for _ in $(seq 1 120); do
    curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && { ok=1; break; }
    kill -0 "$VPID" 2>/dev/null || break
    sleep 10
  done
  if (( ! ok )); then
    kill "$VPID" 2>/dev/null; wait "$VPID" 2>/dev/null; VPID=
    say "vLLM did not start ($tag): $(grep -i -E 'error|exception' "$LOGS/vllm_$tag.log" | tail -n 3 | tr '\n' ' ')"
    exit 1
  fi
  say "vLLM up in $(( $(date +%s) - t0 ))s ($tag: $*)"
  ( peak=0; while kill -0 "$VPID" 2>/dev/null; do
      v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); (( v > peak )) && peak=$v
      echo "$peak" > "$LOGS/vram_peak_$tag"; sleep 5; done ) &
  export LOCAL_LLM_URL="http://127.0.0.1:$PORT/v1"
}
unserve() { kill "$VPID" 2>/dev/null; wait "$VPID" 2>/dev/null; VPID=; }

if [[ $STAGE == *B* ]]; then
  gpu_busy && { say "STOPPED: GPU in use by another process"; nvidia-smi --query-compute-apps=pid,used_memory --format=csv; exit 1; }
  "$VPY" -m e1.chat_lora check --base "$BASE" --train "$TRAIN" --val "$VAL" > "$LOGS/check_$RUN.log" 2>&1 \
    || { say "check FAILED: $(tail -n 3 "$LOGS/check_$RUN.log" | tr '\n' ' ')"; exit 1; }
  say "check $RUN: $(grep -h '^{' "$LOGS/check_$RUN.log" | tr '\n' ' ')"
  rows=$(wc -l < "$ROOT/$TRAIN")
  say "train $RUN: $TRAIN ($rows rows, $(( (rows + 15) / 16 * EPOCHS )) steps), val $VAL, rank $RANK, $EPOCHS epoch(s), gradient checkpointing on"
  # 4096: longest row 3,814 tokens on Run B's data (2026-11-26); a longer row stops the run (no truncation)
  "$VPY" -m e1.chat_lora train --base "$BASE" --train "$TRAIN" --val "$VAL" --rank "$RANK" --epochs "$EPOCHS" \
    --out "$OUT" --max-len 4096 --gate-steps 0 > "$LOGS/train_$RUN.log" 2>&1
  rc=$?
  if (( rc != 0 )); then
    say "train $RUN FAILED rc=$rc: $(grep -h -i -E 'out of memory|error|STOPPED' "$LOGS/train_$RUN.log" | tail -n 3 | tr '\n' ' ')"
    exit 1
  fi
  say "part B done: $(grep -h '^DONE' "$LOGS/train_$RUN.log")"
  say "val loss per epoch: $("$VPY" -c "import json; print(', '.join(f\"{e['epoch']}: {e['val_loss']}\" for e in json.load(open('$OUT/meta.json'))['epochs_done']))")"
fi

if [[ $STAGE == *C* ]]; then
  e=$("$VPY" -c "import json; print(json.load(open('$OUT/meta.json'))['best_epoch_by_val_loss'])")
  say "$RUN: chosen epoch $e (lowest val loss)"
  serve "$RUN" 1 "$MODEL=$OUT/epoch-$e"
  say "part C $RUN"
  "$VPY" -m sim.e5 --models "local:$MODEL" --cases sim/cases_v2 --out experiments/E13 \
    --order-seed 20261128 --full --workers 8 --cap-usd 0.35 --project-after 50 > "$LOGS/e5_$RUN.log" 2>&1
  say "sim.e5 $RUN exit $?: $(grep -E 'PROJECTION|STOPPED|n=' "$LOGS/e5_$RUN.log" | tr '\n' ' ')"
  unserve
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

if [[ $STAGE == *T* ]]; then
  mods=() names=()
  for r in $TF_ALSO $RUN; do
    for d in "$LORA/$r"/epoch-*; do
      [[ -f $d/adapter_config.json ]] || continue
      n=qwen3-4b-e13-$r-e${d##*/epoch-}
      mods+=("$n=$d"); names+=("local:$n")
    done
  done
  (( ${#mods[@]} )) || { say "teacher-forced check: no adapters found"; exit 1; }
  # The first adapter again under a second name: greedy vLLM output depends on what it is batched with (2 of 40
  # decisions differed between 4 names of one adapter, 2026-11-27 smoke), so this pair gives the noise floor.
  mods+=("${mods[0]%%=*}-dup=${mods[0]#*=}"); names+=("${names[0]}-dup")
  serve "tf_$RUN" "${#mods[@]}" "${mods[@]}"
  say "teacher-forced check on $VAL: ${names[*]}"
  "$VPY" -m e1.chat_lora_tf --models "$(IFS=,; echo "${names[*]}")" --val "$VAL" --out experiments/E13/tf.jsonl \
    --workers 8 > "$LOGS/tf_$RUN.log" 2>&1
  say "teacher-forced check exit $?: $(tail -n 1 "$LOGS/tf_$RUN.log")"
  unserve
  say "teacher-forced check done"
fi
say "done; adapters $(du -sh "$OUT" | cut -f1), hf cache $(du -sh "$HF_HOME" | cut -f1), free $(df -h --output=avail "$ROOT" | tail -1)"
