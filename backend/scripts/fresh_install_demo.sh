#!/usr/bin/env bash
# P5 acceptance demo (#24): a stranger clones RUACH and starts it.
#
# Twice from zero: empty directory -> empty SQLite DB -> alembic upgrade head
# -> boot -> health -> first conversation -> protected tool request ->
# persisted approval -> resolution. The two installs' schemas must match.
#
# Uses the stub model runtime: this gate proves the PERSISTENCE layer, not
# sampling quality (that is P2/live-suite territory).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$REPO_ROOT/.venv/bin/python"

run_install() {
  local RUN_DIR="$1"
  echo "=== fresh install in $RUN_DIR ==="
  mkdir -p "$RUN_DIR/workspace"
  printf 'quarterly numbers\n' > "$RUN_DIR/workspace/report.txt"

  local DB_URL="sqlite:///$RUN_DIR/ruach.db"

  # 1. Migration from NOTHING (project configuration mechanism: RUACH_DATABASE_URL).
  RUACH_DATABASE_URL="$DB_URL" "$PY" -m alembic -c "$REPO_ROOT/backend/alembic.ini" upgrade head >/dev/null

  # 2. Verify HEAD.
  local HEAD_EXPECTED HEAD_ACTUAL
  HEAD_EXPECTED=$(cd "$REPO_ROOT/backend" && "$PY" - <<'EOF'
from alembic.script import ScriptDirectory
from alembic.config import Config
cfg = Config("alembic.ini")
heads = ScriptDirectory.from_config(cfg).get_heads()
assert len(heads) == 1, heads
print(heads[0])
EOF
)
  HEAD_ACTUAL=$(RUACH_DATABASE_URL="$DB_URL" "$PY" -m alembic -c "$REPO_ROOT/backend/alembic.ini" current 2>/dev/null | grep -oE '[0-9a-f]{12}' | head -1)
  if [[ "$HEAD_EXPECTED" != "$HEAD_ACTUAL" ]]; then
    echo "FAIL: db head $HEAD_ACTUAL != repository head $HEAD_EXPECTED"; return 1
  fi
  echo "migration head OK: $HEAD_ACTUAL"

  # 3. Boot (startup verifies schema honestly; stub model runtime).
  local PORT=$(( 8300 + RANDOM % 200 ))
  RUACH_DATABASE_URL="$DB_URL" \
  RUACH_WORKSPACE_PATH="$RUN_DIR/workspace" \
  RUACH_AUDIT_LOG_PATH="$RUN_DIR/audit.jsonl" \
  RUACH_MODEL_RUNTIME=stub \
  "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
    >"$RUN_DIR/server.log" 2>&1 &
  local SERVER_PID=$!

  cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
  trap cleanup RETURN

  for _ in $(seq 1 30); do
    curl -sf -m 2 "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1 && break
    sleep 1
  done

  # 4. Health.
  curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null || { echo "FAIL: health"; return 1; }
  echo "health OK"

  # 5. First conversation persists user+assistant messages.
  local RESP CONV_ID
  RESP=$(curl -sf -X POST "http://127.0.0.1:$PORT/api/v1/chat" \
    -H 'Content-Type: application/json' \
    -d '{"message": "Remember the project codename is Falcon."}')
  CONV_ID=$(printf '%s' "$RESP" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["data"]["conversation_id"])')
  echo "conversation created: $CONV_ID"

  # 6. Protected tool request -> persisted PENDING approval.
  RESP=$(curl -sf -X POST "http://127.0.0.1:$PORT/api/v1/chat" \
    -H 'Content-Type: application/json' \
    -d '{"message": "delete report.txt", "conversation_id": "'"$CONV_ID"'"}')
  local AID
  AID=$(printf '%s' "$RESP" | "$PY" -c 'import json,sys; d=json.load(sys.stdin)["data"]; print(d["pending_approval"]["approval_id"])')

  # 7. Resolve the approval through a REAL restart of the process.
  kill "$SERVER_PID"; wait "$SERVER_PID" 2>/dev/null || true
  RUACH_DATABASE_URL="$DB_URL" \
  RUACH_WORKSPACE_PATH="$RUN_DIR/workspace" \
  RUACH_AUDIT_LOG_PATH="$RUN_DIR/audit.jsonl" \
  RUACH_MODEL_RUNTIME=stub \
  "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
    >"$RUN_DIR/server.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 30); do
    curl -sf -m 2 "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1 && break
    sleep 1
  done
  RESP=$(curl -sf -X POST "http://127.0.0.1:$PORT/api/v1/chat/approvals/$AID/approve" \
    -H 'Content-Type: application/json' -d '{"approved": true}')
  printf '%s' "$RESP" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)["data"]
assert d["tool"] and d["tool"]["state"] == "COMPLETED", d
print("approval resolved after restart: COMPLETED")'

  [[ -f "$RUN_DIR/workspace/report.txt" ]] && { echo "FAIL: file still exists"; return 1; }

  # 8. Schema snapshot for cross-run comparison.
  ( cd "$RUN_DIR" && sqlite3 ruach.db ".schema" | grep -v "sqlite_autoindex" | sort ) > "$RUN_DIR/schema.sql"
  echo "install OK"
}

RUN1="$(mktemp -d /tmp/ruach_fresh_run1.XXXXXX)"
RUN2="$(mktemp -d /tmp/ruach_fresh_run2.XXXXXX)"

run_install "$RUN1"
run_install "$RUN2"

if diff -u "$RUN1/schema.sql" "$RUN2/schema.sql"; then
  echo "PASS: both fresh installs reconstructed identical schemas from migrations."
else
  echo "FAIL: schema drift between fresh installs."; exit 1
fi
