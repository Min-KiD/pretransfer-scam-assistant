#!/usr/bin/env bash
# Last server step after E4 phase A and phase B: score everything on the server, so the results exist there even if
# nobody copies them back. Waits until phaseB_status.json says "phaseB" done or failed (a failed run is still scored).
#
#   bash scripts/finalize_open.sh --detach   # setsid + nohup: wait, then run once
#   bash scripts/finalize_open.sh now        # run without waiting
#
# 1. E6: C0 predictions for every E5 session set (the open models' included), experiments/E6/report.md
# 2. E5: experiments/E5/report.md from experiments/E5/sessions.jsonl
# 3. E4: e1.score_e4 -> experiments/E4/{report_A.md,gt_audit.md,summary_A.json}. The closed-model run dirs and
#    data/E1b/real/gt come from the laptop; copy them here first.
# Last line of .cache/logs/finalize.log: "FINAL done" or "FINAL failed: <command>".
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
LOG=$ROOT/.cache/logs/finalize.log
mkdir -p "$(dirname "$LOG")"
if [[ "${1:-}" == "--detach" ]]; then
  setsid nohup bash "$0" wait > "$LOG" 2>&1 < /dev/null &
  echo "started detached pid=$! log=$LOG"
  exit 0
fi
export HOME=$ROOT/.cache/home PYTHONDONTWRITEBYTECODE=1
VPY=$ROOT/.venv-e4/bin/python
B_STATUS=$ROOT/.cache/logs/e4/phaseB_status.json
phaseB_state() { python3 -c "import json;print(json.load(open('$B_STATUS')).get('phaseB',{}).get('state',''))" 2>/dev/null; }
step() {  # label command...
  echo "[$(date -u +%T)] $1"
  shift
  nice -n 15 "$@" || { echo "FINAL failed: $*"; exit 1; }
}

case "${1:-}" in
  wait) until [[ "$(phaseB_state)" =~ ^(done|failed)$ ]]; do sleep 300; done ;;
  now) ;;
  *) sed -n 2,12p "$0"; exit 2 ;;
esac
step "E6: C0 predictions" "$VPY" -m e6.classify predict --model c0 --device cpu
step "E6: report" "$VPY" -m e6.report
step "E5: report" "$VPY" -m sim.e5 --report-only
step "E4: score" "$VPY" -m e1.score_e4 --out experiments/E4
echo "FINAL done"
