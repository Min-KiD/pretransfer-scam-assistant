#!/usr/bin/env bash
# From the laptop: show the detached E1 and E1b server jobs (status + log tails) and pull results back.
#   SERVER=user@host ./scripts/server_status.sh   # override the SERVER= line of .env
set -uo pipefail
SERVER=${SERVER:-$(sed -n 's/^SERVER=//p' "$(dirname "$0")/../.env" 2>/dev/null)}
: "${SERVER:?set SERVER=user@host (env var or a SERVER= line in .env)}"
REMOTE=${REMOTE:-pretransfer-scam-assistant}
cd "$(dirname "$0")/.."

ssh "$SERVER" "cd $REMOTE && echo '== status.json' && cat .cache/logs/status.json 2>/dev/null || echo '(no status yet)';
  echo; echo '== server_run.log'; tail -n 15 .cache/logs/server_run.log 2>/dev/null;
  step=\$(python3 -c 'import json;print(json.load(open(\".cache/logs/status.json\"))[\"step\"])' 2>/dev/null);
  [ -n \"\$step\" ] && { echo; echo \"== \$step.log (tail)\"; grep -v -i warn .cache/logs/\$step.log | tail -n 8; };
  echo; echo '== detached process'; pgrep -af 'scripts/server_run.sh' | grep -v pgrep || echo '(not running)'"

echo; echo "=================== E1b"
ssh "$SERVER" "cd $REMOTE && python3 - <<'EOF' 2>/dev/null || echo '(no E1b status yet)'
import json
s = json.load(open('.cache/logs/e1b/status.json'))
print('pipeline:', s['state'], '| started', s['pipeline_started'], '| updated', s['updated'])
for m, v in s['models'].items():
    print(f\"  {m:22s} {v['state']:8s} {(v.get('reason') or '')[:150]}\")
EOF
  for d in data/E1/runs/T__* data/E1/runs/J__* data/E1b/runs/*__* data/E1b/gen/runs/*__* data/E1b/web_runs/*__*; do
    [ -d \$d ] && echo \"  \$d: \$(ls \$d | wc -l) images\"; done
  cur=\$(ls -t .cache/logs/e1b/*.log 2>/dev/null | head -1); [ -n \"\$cur\" ] && { echo \"== \$cur (tail)\"; grep -v -i -E 'warn|it/s' \$cur | tail -n 4; }
  echo '== extra sets (gen/web)'; python3 -c 'import json;[print(\" \",s,m,v[\"state\"],v[\"reason\"][:120]) for s,d in json.load(open(\".cache/logs/e1b/extra_status.json\")).items() for m,v in d.items()]' 2>/dev/null || echo '  (not started)'
  echo '== detached process'; pgrep -af 'scripts/e1b_(server|extra)_run.sh' | grep -v pgrep || echo '(not running)'"

mkdir -p experiments data/E1 data/E1b
# --update: never overwrite a newer local report (local rescoring is the source of truth for experiments/)
rsync -a --update "$SERVER:$REMOTE/experiments/" experiments/ && echo "== pulled experiments/"
rsync -a "$SERVER:$REMOTE/data/E1/ocr" "$SERVER:$REMOTE/data/E1/runs" data/E1/ 2>/dev/null
rsync -a "$SERVER:$REMOTE/data/E1/env.json" data/E1/ 2>/dev/null
rsync -a "$SERVER:$REMOTE/data/E1b/runs" "$SERVER:$REMOTE/data/E1b/open" data/E1b/ 2>/dev/null
rsync -a "$SERVER:$REMOTE/data/E1b/web_runs" data/E1b/ 2>/dev/null
mkdir -p data/E1b/gen && rsync -a "$SERVER:$REMOTE/data/E1b/gen/runs" data/E1b/gen/ 2>/dev/null
rsync -a "$SERVER:$REMOTE/data/E1b/ocr" data/E1b/ 2>/dev/null
for e in E1 E1b; do
  if [[ -f experiments/$e/SUMMARY.md ]]; then
    echo; echo "== experiments/$e/SUMMARY.md"; cat experiments/$e/SUMMARY.md
  fi
done
exit 0
