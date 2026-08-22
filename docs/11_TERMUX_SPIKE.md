# 11 — Termux Target Validation Spike

One reproducible procedure answering two INDEPENDENT questions on the target
device (itel A6611L, armv7l, Android 15, Termux 0.118.3):

- **QUESTION A** — Can the RUACH Python backend dependency chain install and run?
- **QUESTION B** — Can llama.cpp build and run?

Success of one says NOTHING about the other. Record the result matrix:

| Backend | llama.cpp | Meaning |
|---|---|---|
| PASS | PASS | Strong target viability |
| PASS | FAIL | Backend viable; inference runtime needs architectural decision |
| FAIL | PASS | Inference viable; backend deployment needs architectural decision |
| FAIL | FAIL | Major target-platform review required |

Rules: no architectural pivots based on slowness; only on actual failure.
Keep the phone plugged in; `termux-wake-lock` active.

---

## Part A — Backend spike

Paste into Termux (consent prompts included for system packages):

```bash
termux-wake-lock
echo "RUACH will install build tools (rust, binutils) needed to compile"
echo "pydantic-core from source. This mutates your Termux packages."
pkg install -y rust python-pip ninja || echo "PKG_INSTALL_FAILED"
python --version
python -m venv ~/ruach-venv
source ~/ruach-venv/bin/activate
pip install -U pip wheel
time pip install fastapi uvicorn pydantic-settings sqlalchemy alembic
echo "=== IMPORT TEST ==="
python - <<'PY'
import fastapi, pydantic, sqlalchemy, alembic
import pydantic_core
print("fastapi", fastapi.__version__)
print("pydantic", pydantic.VERSION)
print("pydantic-core", pydantic_core.__version__)
print("sqlalchemy", sqlalchemy.__version__)
print("IMPORTS_OK")
PY
echo "=== APP + SQLITE TEST ==="
mkdir -p ~/.ruach/spike && cd ~/.ruach/spike
cat > spike_app.py <<'PY'
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
PY
nohup python -m uvicorn spike_app:app --host 127.0.0.1 --port 8019 > uv.log 2>&1 &
sleep 6
curl -s http://127.0.0.1:8019/health && echo
pkill -f "uvicorn spike_app"
```

**Backend PASS requires:** installs finish → `IMPORTS_OK` → curl returns
`{"sqlite_read":"ruach"}`.

Record: install duration, any compiler errors, pydantic/pydantic-core versions,
peak behavior if observable.

---

## Part B — llama.cpp spike (resume previous build)

```bash
cd ~/llama.cpp 2>/dev/null || git clone --depth 1 https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp && git rev-parse HEAD > ~/llama_commit.txt && cat ~/llama_commit.txt
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DGGML_OPENMP=ON \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON
time cmake --build build -j2 --target llama-server
ls -lh build/bin/llama-server
# If killed by OOM: rerun ONLY the build line with -j1.
```

Model load + inference happens after model transfer (Part C). Boot test once
the GGUF is on-device:

```bash
~/.ruach/runtime/llama-server -m ~/.ruach/models/qwen3-0.6b/Qwen3-0.6B-Q8_0.gguf \
  --host 127.0.0.1 --port 8080 &
sleep 15
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say RUACH_READY"}],"max_tokens":20}'
```

Record: commit SHA, build duration, binary size, load time, response, stability.

---

## Part C — Model transfer (validation artifact, never committed)

Preferred (USB debugging available):

```bash
# On MacBook:
adb push ~/.ruach/models/qwen3-0.6b/Qwen3-0.6B-Q8_0.gguf /sdcard/Download/
# On Termux (once):
termux-setup-storage
mkdir -p ~/.ruach/models/qwen3-0.6b
cp /sdcard/Download/Qwen3-0.6B-Q8_0.gguf ~/.ruach/models/qwen3-0.6b/
sha256sum ~/.ruach/models/qwen3-0.6b/Qwen3-0.6B-Q8_0.gguf
```

Fallback: `pkg install openssh` on Termux, `sshd`, then
`scp` from the Mac. Any mechanism is fine — RUACH only cares that the file
exists at the configured path.

**Expected SHA-256 (must match):**
`9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031`
(source: measured MacBook download, 2026-08-23)

---

## Reporting template

```text
Backend:   PASS / FAIL   (installs / imports / startup / sqlite)
llama.cpp: PASS / FAIL   (build / binary / model load / inference)
Transfer:  PASS / FAIL   (sha256 match Y/N)
Inference: PASS / FAIL   (real completion produced Y/N)
```

After evidence arrives: update docs/10 §7 statuses, fill observed memory and
tokens/sec into the model registry, then — and only then — decide 7c's
target-specific half.
