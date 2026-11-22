#!/usr/bin/env bash
# E4 phase B on the server: LoRA runs B2_500, B2_2000, B1, B3 with e1.lora_train, each evaluated through vLLM + e1.e4_run
# (B4 is an OCR cross-check of B1's outputs in e1.score_e4, no training here).
#
#   bash scripts/e4_phaseB.sh --detach     # unattended, after phase A: setsid + nohup; rerun any time (resumable)
#   bash scripts/e4_phaseB.sh check        # CPU smoke test: prompt layout, masking, image tokens
#
# `all` (what --detach runs):
# 0. wait until phase A is finished (phaseA_status.json "phaseA" done, or its lock is free and every QUEUE model is
#    done/failed) and no other process is on the GPU (never kill anything). Unless BASE_NAME is given, the base is
#    `python -m e1.lora_train pick-base <phase-A models that finished>`: highest J string match on web-dev
#    (.cache/e4/lora/base_pick.json)
# 1. PP-OCRv6 GPU text for data/E4/{train,val,val_la} as phase A step 0 does it (needed by B3 and its JO inference)
# 2. per run, cheapest first; a run whose meta.json says finished is not trained again:
#    a. train -> .cache/e4/lora/<run>/{log.jsonl,meta.json,ckpt-<step>/}
#    b. vllm serve the base (served as $BASE_NAME) with every checkpoint as a LoRA module <run>-<step>, so
#       `--model local:<run>-<step>` in e1.e4_run (core.llm: "local:<name>" -> model "<name>" at $LOCAL_LLM_URL) hits it
#    c. selection pass per checkpoint: val with --workers 4, web with --workers 1 (web-dev picks; the picked
#       checkpoint's web-test latency then comes from a 1-at-a-time run, as in phase A)
#    d. python -m e1.lora_train pick --run <run> -> pick.json ("config" = picked e4_run config)
#    e. picked checkpoint, --workers 1, on E1,E1b,gen,gen_ref,val_la
#    f. once per server (resumable, so later servers skip it): the base model on val,val_la in J and JO, --workers 4,
#       so every B row has a same-set baseline
#    g. stop vLLM
# Progress: .cache/logs/e4/phaseB.log, .cache/logs/e4/phaseB_status.json, per step .cache/logs/e4/B_*.log
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOGS=$ROOT/.cache/logs/e4
OUT=$ROOT/.cache/e4/lora
mkdir -p "$LOGS" "$OUT"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" all > "$LOGS/phaseB.log" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOGS/phaseB.log"
  exit 0
fi

export HOME=$ROOT/.cache/home HF_HOME=$ROOT/.cache/hf HF_HUB_OFFLINE=1 XDG_CACHE_HOME=$ROOT/.cache/xdg \
  TMPDIR=$ROOT/.cache/tmp PADDLE_PDX_CACHE_HOME=$ROOT/.cache/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
VPY=$ROOT/.venv-e4/bin/python                                   # torch/peft training, vllm, e1.e4_run
HPY=${HPY:-/home/intern/vidoc-dev/.venvs/mineru/bin/python}      # PP-OCRv6 env from E1b, used read-only
BASE_NAME=${BASE_NAME:-}                                        # empty: phase-A winner by e1.lora_train pick-base
RUNS=${RUNS:-"B2_500 B2_2000 B1 B3"}
QUEUE=${QUEUE:-"qwen3-vl-4b qwen3-vl-2b qwen3.5-4b"}           # phase A's queue (to know when it is over)
PORT=${PORT:-8000}
STATUS=$LOGS/phaseB_status.json
A_STATUS=$LOGS/phaseA_status.json

status() {  # key state detail
  python3 - "$STATUS" "$1" "$2" "$3" <<'EOF'
import json, sys, datetime, os
p, k, st, d = sys.argv[1:]
s = json.load(open(p)) if os.path.exists(p) else {}
s[k] = {"state": st, "detail": d, "t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
json.dump(s, open(p + ".tmp", "w"), indent=1)
os.replace(p + ".tmp", p)
EOF
  echo "[$(date -u +%T)] $1: $2 $3"
}
state_of() { python3 -c "import json;print(json.load(open('$1')).get('$2',{}).get('state',''))" 2>/dev/null; }
gpu_busy() { [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)" ]]; }
wait_gpu() { while gpu_busy; do status "$1" waiting "GPU in use by another process"; sleep 300; done; }
base_repo() { "$VPY" -c "from e1.open_models import MODELS; print(MODELS['$BASE_NAME']['repos'][0])"; }
base_path() { "$VPY" -c "from e1.open_models import snapshot; print(snapshot('$(base_repo)', download=False))"; }
finished() { [[ -f $OUT/$1/meta.json ]] && "$VPY" -c "import json,sys; sys.exit(not json.load(open('$OUT/$1/meta.json')).get('finished'))"; }
steps_of() { "$VPY" -c "import json; print(' '.join(sorted(json.load(open('$OUT/$1/meta.json'))['checkpoints'], key=int)))"; }
picked() { "$VPY" -c "import json; print(json.load(open('$OUT/$1/pick.json'))['step'])"; }

phaseA_over() {
  [[ "$(state_of "$A_STATUS" phaseA)" == done ]] && return 0
  flock -n "$LOGS/phaseA.lock" true 2>/dev/null || return 1        # e4_phaseA.sh still running
  for m in $QUEUE; do [[ "$(state_of "$A_STATUS" "$m")" =~ ^(done|failed)$ ]] || return 1; done
}

train_args() {
  case $1 in
    # 4000 images / (batch 1 x accum 8) = 500 steps; val loss + adapter every 125 steps
    B1) echo "--eval-every 125 --save-every 125" ;;
    # learning curve: the first 500 / 2000 of the same seeded shuffle (63 and 250 steps)
    B2_500) echo "--n-train 500 --eval-every 16 --save-every 16" ;;
    B2_2000) echo "--n-train 2000 --eval-every 50 --save-every 50" ;;
    B3) echo "--ocr --eval-every 125 --save-every 125" ;;
    *) return 1 ;;
  esac
}

VPID=""
serve() {  # run: base + all of the run's checkpoints as LoRA modules; returns 1 if vLLM does not come up
  local run=$1 mods=() n=0
  for s in $(steps_of "$run"); do mods+=("$run-$s=$OUT/$run/ckpt-$s"); n=$((n + 1)); done
  wait_gpu "$run"
  "$VPY" -m vllm.entrypoints.openai.api_server --model "$(base_path)" --served-model-name "$BASE_NAME" \
    --host 127.0.0.1 --port "$PORT" --max-model-len 16384 --gpu-memory-utilization 0.88 --max-num-seqs 8 \
    --limit-mm-per-prompt '{"image":1}' --mm-processor-kwargs '{"max_pixels":2097152}' \
    --enable-lora --max-lora-rank 16 --max-loras "$n" --max-cpu-loras "$n" --lora-modules "${mods[@]}" \
    > "$LOGS/B_$run.vllm.log" 2>&1 &
  VPID=$!
  for _ in $(seq 1 120); do
    curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && return 0
    kill -0 "$VPID" 2>/dev/null || break
    sleep 10
  done
  stop_server
  return 1
}
stop_server() { [[ -n $VPID ]] && { kill "$VPID" 2>/dev/null; wait "$VPID" 2>/dev/null; VPID=""; }; }
trap stop_server EXIT
e4() {  # model mode sets workers logname
  "$VPY" -m e1.e4_run --model "local:$1" --mode "$2" --sets "$3" --workers "$4" >> "$LOGS/B_$5.e4.log" 2>&1
}

run_all() {
  exec 9> "$LOGS/phaseB.lock"
  flock -n 9 || { echo "another e4_phaseB.sh is running"; exit 1; }
  while ! phaseA_over; do status phaseB waiting "phase A not finished"; sleep 300; done
  if [[ -z $BASE_NAME ]]; then
    cands=""; for m in $QUEUE; do [[ "$(state_of "$A_STATUS" "$m")" == done ]] && cands="$cands $m"; done
    [[ -n $cands ]] || { status phaseB failed "no phase-A model finished"; exit 1; }
    BASE_NAME=$("$VPY" -m e1.lora_train pick-base $cands 2> "$LOGS/B_base_pick.log" | tail -n 1) \
      || { status phaseB failed "pick-base: $(tail -n 1 "$LOGS/B_base_pick.log")"; exit 1; }
    status phaseB running "base $BASE_NAME (pick-base over$cands)"
  fi
  for s in train val val_la; do
    d=data/E4/$s
    if [[ $(ls "$d/images" | wc -l) -ne $(wc -l < "$d/manifest.jsonl") || \
          $(ls "$d/gt" 2>/dev/null | wc -l) -ne $(wc -l < "$d/manifest.jsonl") ]]; then
      status phaseB failed "$d incomplete (images/gt vs manifest): sync data/E4 first"; exit 1
    fi
  done
  base_path > /dev/null 2>&1 || { status phaseB failed "$BASE_NAME weights not on disk"; exit 1; }

  # ---------------------------------------------------------------- 1. PP-OCRv6 on the E4 sets
  wait_gpu ocr
  status ocr running "PP-OCRv6 GPU on train,val,val_la"
  PYTHONPATH=$ROOT/.cache/pylib:$ROOT "$HPY" -m e1.open_models run --model pp-ocrv6-gpu --mode T \
    --sets train,val,val_la --budget-min 600 --min-images 0 > "$LOGS/B_ocr.log" 2>&1 \
    && status ocr done "$(tail -n 1 "$LOGS/B_ocr.log")" \
    || status ocr failed "$(tail -n 2 "$LOGS/B_ocr.log" | tr '\n' ' ')"

  export LOCAL_LLM_URL="http://127.0.0.1:$PORT/v1"
  for run in $RUNS; do
    mode=J; [[ $run == B3 ]] && mode=JO
    # ------------------------------------------------------------ 2a. train
    if ! finished "$run"; then
      wait_gpu "$run"
      status "$run" running "train"
      # shellcheck disable=SC2046
      "$VPY" -m e1.lora_train train --base "$(base_path)" --out "$OUT/$run" $(train_args "$run") \
        > "$LOGS/B_$run.train.log" 2>&1
      finished "$run" || { status "$run" failed "train: $(tail -n 2 "$LOGS/B_$run.train.log" | tr '\n' ' ')"; continue; }
    fi
    # ------------------------------------------------------------ 2b-g. evaluate
    status "$run" running "vllm serve with $(steps_of "$run" | wc -w) adapters"
    serve "$run" || { status "$run" failed "vllm did not start: $(grep -i -E 'error|exception' \
      "$LOGS/B_$run.vllm.log" | tail -n 2 | tr '\n' ' ')"; continue; }
    for s in $(steps_of "$run"); do
      status "$run" running "selection pass ckpt $s"
      e4 "$run-$s" "$mode" val 4 "$run"
      e4 "$run-$s" "$mode" web 1 "$run"
    done
    if "$VPY" -m e1.lora_train pick --run "$run" > "$LOGS/B_$run.pick.log" 2>&1; then
      p=$(picked "$run")
      status "$run" running "picked step $p: E1,E1b,gen,gen_ref,val_la"
      e4 "$run-$p" "$mode" E1,E1b,gen,gen_ref,val_la 1 "$run"
    else
      status "$run" failed "pick: $(tail -n 2 "$LOGS/B_$run.pick.log" | tr '\n' ' ')"
    fi
    status "$run" running "base $BASE_NAME on val,val_la (J, JO)"
    e4 "$BASE_NAME" J val,val_la 4 base
    e4 "$BASE_NAME" JO val,val_la 4 base
    stop_server
    [[ "$(state_of "$STATUS" "$run")" == failed ]] || status "$run" done "$(tail -n 1 "$LOGS/B_$run.pick.log")"
  done
  status phaseB done "adapters $(du -sh "$OUT" | cut -f1), free $(df -h --output=avail "$ROOT" | tail -1)"
}

case "${1:-}" in
  all) run_all ;;
  check) BASE_NAME=${BASE_NAME:-qwen3-vl-4b}
    CUDA_VISIBLE_DEVICES= nice -n 15 "$VPY" -m e1.lora_train check --base "$(base_repo)" --n 4 ;;
  *) sed -n 2,24p "$0"; exit 2 ;;
esac
