#!/usr/bin/env bash
# Pack everything that is not in git (data/, plus weights/ if present) into one archive for Google Drive.
#   ./scripts/pack_data.sh              -> ../drive_upload/pretransfer-data-YYYYMMDD.tar.gz
# Teammates: download the archive and unpack it at the repo root:  tar -xzf pretransfer-data-YYYYMMDD.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${OUT:-../drive_upload}
mkdir -p "$OUT"
NAME="$OUT/pretransfer-data-$(date +%Y%m%d).tar.gz"
DIRS=(data)
[[ -d weights ]] && DIRS+=(weights)
# data/app is the local SQLite of the sample app; every machine creates its own.
tar --exclude='data/app' --exclude='__pycache__' -czf "$NAME" "${DIRS[@]}"
du -h "$NAME"
