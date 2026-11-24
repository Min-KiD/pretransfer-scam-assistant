#!/usr/bin/env bash
# E10 part C on the laptop: Claude Haiku 5.5 through the native Anthropic API (core.llm "anthropic:"). One Claude cap
# of $CAP USD covers all of part C (Anthropic + the Gemini simulated user of the chat step) and the Anthropic cost of
# the Haiku arms of part D (planner, 2026-11-24). The cap was 2.0 USD; Minh raised it to 2.6 on 2026-11-24 (via the
# planner) so the Haiku part D arms can finish all 300 cases. Steps, in the planner's order of priority (2026-11-24):
#   1. screenshots, E4 mode J (= E1 method B: image -> JSON, schema constrained) on `web`, 1 request at a time
#   2. chat: E5 on the 300 cases (`tu_do`), after any other sim.e5 run has finished (they share sessions.jsonl)
#   3. part D Haiku arms: split + merged with Haiku as reader and chat (sim.e10_d checks both caps itself)
#   4. screenshots on the other sets with what is left, 8 at a time, in the order gen_ref, gen, E1b, E1; stop at 95% of
#      the cap and log which sets did not run
# Spend is read back from the run files before each step, so a rerun resumes.
#   bash scripts/e10_partC.sh > .cache/logs/e10/partC.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
M=anthropic:claude-haiku-5-5
CAP=${CAP:-2.6}
left() {  # cap at 95% minus part C spend minus the Anthropic spend of part D
  "$PY" - "$CAP" <<'EOF'
import json, sys
from sim.e10_d import OUT, part_c_spend, spend_split
p = OUT / "sessions.jsonl"
d = sum(spend_split(r)["claude"] for r in map(json.loads, open(p, encoding="utf-8")) if "preds" in r) if p.exists() else 0
print(f"{max(0.0, 0.95 * float(sys.argv[1]) - part_c_spend() - d):.4f}")
EOF
}
echo "[$(date +%T)] part C start, left $(left) of 95% of $CAP USD"
"$PY" -m e1.e4_run --model "$M" --mode J --sets web --workers 1 --max-tokens 8192 --cap-usd "$(left)"
while pgrep -f "sim.e5 --models" > /dev/null; do sleep 30; done
echo "[$(date +%T)] chat, left $(left) USD"
"$PY" -m sim.e5 --models "$M" --full --workers 8 --cap-usd "$(left)"
echo "[$(date +%T)] part D Haiku arms, left $(left) USD (log .cache/logs/e10/partD_haiku.log)"
"$PY" -m sim.e10_d --arms split,merged --chat "$M" --reader "$M" --claude-cap-usd "$CAP" --workers 8 \
  >> .cache/logs/e10/partD_haiku.log 2>&1
grep -h "STOPPED" .cache/logs/e10/partD_haiku.log | tail -n 1
stopped=0
not_run=()
for s in gen_ref gen E1b E1; do
  l=$(left)
  awk "BEGIN{exit !($l < 0.01)}" && stopped=1
  (( stopped )) && { not_run+=("$s"); continue; }
  echo "[$(date +%T)] screenshots $s, left $l USD"
  # tee -a: /dev/stderr is the log file itself, and plain tee would truncate it
  out=$("$PY" -m e1.e4_run --model "$M" --mode J --sets "$s" --workers 8 --max-tokens 8192 --cap-usd "$l" | tee -a /dev/stderr)
  grep -q '"cap_stop": true' <<< "$out" && { echo "cap reached inside $s: partial"; stopped=1; }
done
(( ${#not_run[@]} )) && echo "not run (cap reached): ${not_run[*]}"
echo "[$(date +%T)] part C done, left $(left) USD"
