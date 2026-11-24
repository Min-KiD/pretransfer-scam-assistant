#!/usr/bin/env bash
# E10 part C on the laptop: Claude Haiku 5.5 through the native Anthropic API (core.llm "anthropic:"), one cap of
# $CAP USD for the whole part (Anthropic + the Gemini simulated user), shared across the steps below.
#   1. screenshots, E4 mode J (= E1 method B: image -> JSON, schema constrained) on `web`, 1 request at a time
#   2. chat: E5 on the 300 cases (`tu_do`), after any other sim.e5 run has finished (they share sessions.jsonl)
#   3. screenshots on the other sets, 8 at a time
# Each step gets the cap minus what part C has spent so far (read back from the run files, so a rerun resumes).
#   bash scripts/e10_partC.sh > .cache/logs/e10/partC.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
M=anthropic:claude-haiku-5-5
CAP=${CAP:-2.0}
left() {
  "$PY" - "$CAP" <<'EOF'
import json, sys
from pathlib import Path
from e1.vlm import RUN_DIRS
spent = 0.0
for d in RUN_DIRS.values():
    for p in Path(d, "J__claude-haiku-5-5").glob("*.json"):
        spent += json.loads(p.read_text(encoding="utf-8")).get("usd") or 0
sp = Path("experiments/E5/sessions.jsonl")
for line in open(sp, encoding="utf-8"):
    r = json.loads(line)
    if r.get("model") == "anthropic:claude-haiku-5-5" and "preds" in r:
        spent += r["usd"] + r.get("victim_usd", 0)
print(f"{max(0.0, float(sys.argv[1]) - spent):.4f}")
EOF
}
echo "[$(date +%T)] part C start, left $(left) of $CAP USD"
"$PY" -m e1.e4_run --model "$M" --mode J --sets web --workers 1 --max-tokens 8192 --cap-usd "$(left)"
while pgrep -f "sim.e5 --models" > /dev/null; do sleep 30; done
echo "[$(date +%T)] chat, left $(left) USD"
"$PY" -m sim.e5 --models "$M" --full --workers 8 --cap-usd "$(left)"
echo "[$(date +%T)] other sets, left $(left) USD"
"$PY" -m e1.e4_run --model "$M" --mode J --sets E1,E1b,gen,gen_ref --workers 8 --max-tokens 8192 --cap-usd "$(left)"
echo "[$(date +%T)] part C done, left $(left) of $CAP USD"
