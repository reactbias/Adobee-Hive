#!/usr/bin/env bash
# Starts a hub with the CV-based candidates, seeds them, and leaves it running on :8000.
# Then start the frontend (documentation/HIRING.md). PY defaults to .venv/bin/python; set HIVE_PY to override.
set -euo pipefail
cd "$(dirname "$0")"
PY="${HIVE_PY:-.venv/bin/python}"
export FOLDER_ROOT="$(pwd)/../../testdata/candidates" ADMISSION_POLICY=open LLM_PROVIDER=offline
export DUCKDB_PATH="$(pwd)/data/hiring.duckdb"
rm -f "$DUCKDB_PATH" "$DUCKDB_PATH.wal"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
HUB=$!
trap 'kill $HUB' EXIT
sleep 8
"$PY" tools/seed_vaults.py --vaults ../../testdata/candidates
echo "The hub is on http://127.0.0.1:8000 with the candidates published. Ctrl+C stops it."
wait $HUB
