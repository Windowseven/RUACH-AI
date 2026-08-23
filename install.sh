#!/bin/sh
# RUACH installer for development hosts (macOS / Linux).
# Target-device (Termux) installation is validated separately — no
# platform branches live here by design (docs/13).
set -eu

cd "$(dirname "$0")"

echo "[install] RUACH v$(cat bootstrap/version.py | sed -n 's/.*\"\(.*\)\".*/\1/p')"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on PATH" >&2
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[install] python        : $PYTHON_VERSION"

if [ ! -d .venv ]; then
    echo "[install] creating venv : .venv"
    python3 -m venv .venv
fi

echo "[install] backend deps  : pip install -e ./backend"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ./backend

if command -v npm >/dev/null 2>&1; then
    echo "[install] ui            : npm ci && npm run build (dev-time only)"
    (cd frontend && npm ci --no-audit --no-fund && npm run build)
else
    echo "[install] ui            : npm not found — UI will be unbuilt;"
    echo "                          API still works. Install Node 20+ and run:"
    echo "                          cd frontend && npm ci && npm run build"
fi

echo "[install] doctor check  :"
./ruach doctor || true

cat <<'EOF'

Next steps:
  1. ./ruach setup          # fetch llama.cpp runtime + a model (guided)
  2. ./ruach start          # serves http://127.0.0.1:8018
  3. ./ruach status|stop    # lifecycle commands
  4. ./ruach verify         # full local MVP gate
EOF
