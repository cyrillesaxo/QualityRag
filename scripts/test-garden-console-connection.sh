#!/usr/bin/env bash
# Studio -> Vite proxy -> real Python Garden engine acceptance.
# Runs on ephemeral loopback ports in CI. No production endpoint or credentials.
set -euo pipefail

workdir="$(mktemp -d)"
engine_pid=""
vite_pid=""
cleanup() {
  if [[ -n "$vite_pid" ]]; then kill "$vite_pid" 2>/dev/null || true; fi
  if [[ -n "$engine_pid" ]]; then kill "$engine_pid" 2>/dev/null || true; fi
  rm -rf "$workdir"
}
trap cleanup EXIT

mkdir -p "$workdir/receipts"
python tools/research_ledger/cli.py --db "$workdir/ledger.sqlite" init

export QUALITYRAG_GARDEN_TOKEN="ci-only-garden-console-engine-token-2026"
export QUALITYRAG_RESEARCH_DB="$workdir/ledger.sqlite"
export QUALITYRAG_GARDEN_RECEIPT_DIR="$workdir/receipts"
export QUALITYRAG_GARDEN_PORT=5057

python tools/semantic_store/rct_garden_http.py > "$workdir/engine.log" 2>&1 &
engine_pid=$!
npm --prefix apps/studio run dev -- --host 127.0.0.1 --port 5173 --strictPort \
  > "$workdir/vite.log" 2>&1 &
vite_pid=$!

base="http://127.0.0.1:5173/garden"
ready=0
for _ in $(seq 1 40); do
  if curl -fsS --max-time 2 \
       -H "Authorization: Bearer $QUALITYRAG_GARDEN_TOKEN" \
       "$base/status" -o "$workdir/status.json"; then
    ready=1
    break
  fi
  if ! kill -0 "$engine_pid" 2>/dev/null || ! kill -0 "$vite_pid" 2>/dev/null; then
    echo "One of the actual services exited during connection setup" >&2
    cat "$workdir/engine.log" "$workdir/vite.log" >&2
    exit 1
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "Studio never connected to the Garden engine" >&2
  cat "$workdir/engine.log" "$workdir/vite.log" >&2
  exit 1
fi

curl -fsS --max-time 10 \
  -H "Authorization: Bearer $QUALITYRAG_GARDEN_TOKEN" \
  "$base/projection" -o "$workdir/projection.json"

curl -fsS --max-time 30 \
  -H "Authorization: Bearer $QUALITYRAG_GARDEN_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{}' "$base/self-test" -o "$workdir/self-test.json"

# Do not accidentally accept unauthorized calls via the proxy.
unauthorized_status="$(curl --max-time 10 -s -o /dev/null -w '%{http_code}' \
   -H "Authorization: Bearer wrong-token" "$base/projection")"
[[ "$unauthorized_status" == "401" ]] || {
  echo "Expected 401 through Studio proxy, got: $unauthorized_status" >&2
  exit 1
}

python - "$workdir" <<'PY'
import json
from pathlib import Path
import sys

directory = Path(sys.argv[1])
status = json.loads((directory / "status.json").read_text())
projection = json.loads((directory / "projection.json").read_text())
test = json.loads((directory / "self-test.json").read_text())

assert status["schema"] == "rct.garden-engine-status/v0.1"
assert status["connected"] is True
assert status["ledger_integrity"] == "CONSISTENT"
assert status["production_ready"] is False

assert projection["schema"] == "rct.semantic-gardener-projection/v0.1"
assert projection["ledger_integrity"] == "CONSISTENT"
assert projection["promotion_authorized"] is False

assert test["schema"] == "rct.garden-engine-self-test/v0.1"
assert test["status"] == "PASS"
assert test["paired_candidates"] == 6
assert test["synthetic_test_only"] is True
assert test["ledger_persisted"] is False
assert test["qualityrag_admission"] == "INCONCLUSIVE"
assert test["promotion_authorized"] is False

print("PASS: Studio Vite proxy -> authenticated Garden engine -> actual bounded controller")
print("PASS: read-only ledger projection, 401 rejection, zero unauthorized promotion")
PY
