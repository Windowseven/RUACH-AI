#!/data/data/com.termux/files/usr/bin/bash
#
# termux_spike.sh - RUACH target validation spike (docs/11_TERMUX_SPIKE.md)
# Runs on the PHONE inside Termux. Tees everything to ~/spike_results.txt
# Send that file back to the project afterwards.
#
set -uo pipefail

RESULTS="$HOME/spike_results.txt"
LLAMA_DIR="$HOME/llama.cpp"
RUNTIME_BIN="$HOME/.ruach/runtime/llama-server"
MODEL="$HOME/.ruach/models/qwen3-0.6b/Qwen3-0.6B-Q8_0.gguf"
EXPECTED_SHA="9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031"

rm -f "$RESULTS"
exec > >(tee -a "$RESULTS") 2>&1
echo "=============================================="
echo "RUACH SPIKE - $(date)"
echo "=============================================="
echo "-- device --"
uname -a
getprop ro.product.model 2>/dev/null || true
free -m 2>/dev/null || head -3 /proc/meminfo
df -h "$HOME" | tail -1
python --version 2>&1 || true

BACKEND_STATUS=FAIL
LLAMA_BUILD_STATUS=FAIL
TRANSFER_STATUS=FAIL
INFERENCE_STATUS=FAIL

echo ""
echo "############ PART A: BACKEND ############"
termux-wake-lock 2>/dev/null || true
echo "Consent: install build tools (rust, python-pip, ninja, binutils)?"
echo "This compiles pydantic-core from source and mutates Termux packages."
read -r -p "Proceed? [y/N] " ANSWER
if [ "$ANSWER" = "y" ] || [ "$ANSWER" = "Y" ]; then
    pkg install -y rust python-pip ninja binutils || echo "PKG_INSTALL_FAILED"
else
    echo "PKG_INSTALL_SKIPPED_BY_USER"
fi

echo "=== A1: venv + installs ==="
if python -m venv ~/ruach-venv && source ~/ruach-venv/bin/activate; then
    pip install -U pip wheel
    time pip install fastapi uvicorn pydantic-settings sqlalchemy alembic \
        && echo "PIP_INSTALL_OK" || echo "PIP_INSTALL_FAILED"
    echo "=== A2: import test ==="
    python - <<'PYEOF' && echo "IMPORTS_OK" || echo "IMPORTS_FAILED"
import fastapi, pydantic, sqlalchemy, alembic
import pydantic_core
print("fastapi", fastapi.__version__)
print("pydantic", pydantic.VERSION)
print("pydantic-core", pydantic_core.__version__)
print("sqlalchemy", sqlalchemy.__version__)
PYEOF
else
    echo "VENV_FAILED"
fi

echo "=== A3: app + sqlite roundtrip ==="
mkdir -p ~/.ruach/spike && cd ~/.ruach/spike || exit 1
cat > spike_app.py <<'PYEOF'
from fastapi import FastAPI
import sqlalchemy as sa

engine = sa.create_engine("sqlite:///spike.db")
with engine.begin() as conn:
    conn.execute(sa.text("CREATE TABLE IF NOT EXISTS t (v TEXT)"))
    conn.execute(sa.text("INSERT INTO t VALUES ('ruach')"))

app = FastAPI()

@app.get("/health")
def health():
    with engine.connect() as conn:
        value = conn.execute(sa.text("SELECT v FROM t LIMIT 1")).scalar()
    return {"sqlite_read": value}
PYEOF
nohup python -m uvicorn spike_app:app --host 127.0.0.1 --port 8019 > uv.log 2>&1 &
sleep 8
HEALTH=$(curl -s http://127.0.0.1:8019/health)
echo "HEALTH_RESPONSE: $HEALTH"
pkill -f "uvicorn spike_app" 2>/dev/null
[ "$HEALTH" = '{"sqlite_read":"ruach"}' ] && BACKEND_STATUS=PASS
cd "$HOME"

echo ""
echo "############ PART B: LLAMA.CPP BUILD ############"
cd "$LLAMA_DIR" 2>/dev/null \
    || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
cd "$LLAMA_DIR" || exit 1
git rev-parse HEAD | tee ~/llama_commit.txt

echo "=== B1: configure ==="
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DGGML_OPENMP=ON \
    -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON \
    && echo "CONFIGURE_OK" || echo "CONFIGURE_FAILED"

echo "=== B2: build llama-server (-j2; if OOM-killed, rerun with: J1=1 bash termux_spike.sh) ==="
JOBS=2
[ "${J1:-0}" = "1" ] && JOBS=1
time cmake --build build -j"$JOBS" --target llama-server \
    && echo "BUILD_OK" || echo "BUILD_FAILED"

if [ -x build/bin/llama-server ]; then
    ls -lh build/bin/llama-server
    mkdir -p ~/.ruach/runtime
    cp build/bin/llama-server "$RUNTIME_BIN"
    echo "INSTALLED_TO: $RUNTIME_BIN"
    LLAMA_BUILD_STATUS=PASS
fi

echo ""
echo "############ PART C: MODEL VERIFY + BOOT TEST ############"
if [ -f "$MODEL" ]; then
    ACTUAL_SHA=$(sha256sum "$MODEL" | awk '{print $1}')
    echo "MODEL_SHA: $ACTUAL_SHA"
    [ "$ACTUAL_SHA" = "$EXPECTED_SHA" ] && TRANSFER_STATUS=PASS || TRANSFER_STATUS=FAIL
else
    echo "MODEL_MISSING: $MODEL (run push_model.sh on the MacBook first)"
fi

if [ "$TRANSFER_STATUS" = "PASS" ] && [ "$LLAMA_BUILD_STATUS" = "PASS" ]; then
    echo "=== C1: boot llama-server + real completion (this is the big one) ==="
    cd "$HOME/.ruach/spike" || exit 1
    nohup "$RUNTIME_BIN" -m "$MODEL" --host 127.0.0.1 --port 8080 \
        -c 2048 -t 4 > llama.log 2>&1 &
    echo "waiting for model load (up to 90s)..."
    for i in $(seq 1 30); do
        sleep 3
        curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1 && break
    done
    echo "HEALTH: $(curl -s http://127.0.0.1:8080/health)"
    echo "--- completion request ---"
    RESPONSE=$(curl -s http://127.0.0.1:8080/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{"messages":[{"role":"user","content":"Say RUACH_READY"}],"max_tokens":20}')
    echo "RESPONSE: $RESPONSE"
    pkill -f llama-server 2>/dev/null
    case "$RESPONSE" in
        *RUACH_READY*|*"content"*) INFERENCE_STATUS=PASS ;;
    esac
fi

echo ""
echo "############ RESULT MATRIX ############"
echo "Backend:   $BACKEND_STATUS"
echo "llama.cpp: $LLAMA_BUILD_STATUS"
echo "Transfer:  $TRANSFER_STATUS"
echo "Inference: $INFERENCE_STATUS"
echo ""
echo "Full log saved to: $RESULTS"
echo "Send spike_results.txt back to the project."
termux-wake-unlock 2>/dev/null || true
exit 0
