#!/usr/bin/env bash
#
# push_model.sh — transfer the verified Qwen3-0.6B GGUF from this project's
# staging area to the Android/Termux target.
#
# Canonical procedure: docs/11_TERMUX_SPIKE.md Part C.
# Rule: the development host STAGES the model; it never executes it.
#
# Usage:
#   ./staging/push_model.sh                 # adb route (USB debugging)
#   ./staging/push_model.sh --scp USER@HOST # scp route (Termux sshd)
#   ./staging/push_model.sh --dry-run       # print plan, change nothing
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_ID="qwen3-0.6b"
FILE_NAME="Qwen3-0.6B-Q8_0.gguf"
SRC="$SCRIPT_DIR/models/$MODEL_ID/$FILE_NAME"
SHA_FILE="$SCRIPT_DIR/models/$MODEL_ID/sha256.txt"
SDCARD_DIR="/sdcard/Download"
DEVICE_REL_HOME=".ruach/models/$MODEL_ID"

MODE="adb"
SCP_TARGET=""
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --scp)
            SCP_TARGET="${2:?--scp requires USER@HOST}"
            MODE="scp"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

run() {
    echo "+ $*"
    if [ "$DRY_RUN" -eq 0 ]; then
        "$@"
    fi
}

echo "== RUACH model transfer =="
echo "Route : $MODE"

if [ ! -f "$SRC" ]; then
    echo "MISSING: $SRC" >&2
    exit 1
fi
if [ ! -f "$SHA_FILE" ]; then
    echo "MISSING: $SHA_FILE (staging kit incomplete)" >&2
    exit 1
fi

EXPECTED_SHA="$(awk '{print $1}' "$SHA_FILE" | tr -d '[:space:]')"
if [ ${#EXPECTED_SHA} -ne 64 ]; then
    echo "INVALID sha256.txt contents: '$EXPECTED_SHA'" >&2
    exit 1
fi

echo "Verifying local artifact integrity..."
LOCAL_SHA="$(shasum -a 256 "$SRC" | awk '{print $1}')"
if [ "$LOCAL_SHA" != "$EXPECTED_SHA" ]; then
    echo "ABORT: local file hash mismatch" >&2
    echo "  expected: $EXPECTED_SHA" >&2
    echo "  actual  : $LOCAL_SHA" >&2
    exit 1
fi
echo "OK ($EXPECTED_SHA)"
SIZE_MB=$(( $(stat -f %z "$SRC" 2>/dev/null || stat -c %s "$SRC") / 1024 / 1024 ))
echo "Size  : ${SIZE_MB} MB"

if [ "$MODE" = "adb" ]; then
    echo
    echo "-- Route A: adb -> shared storage, finalize inside Termux --"
    run adb devices
    run adb push "$SRC" "$SDCARD_DIR/$FILE_NAME"
    cat <<EOF

Now on the phone, inside Termux, run:

  termux-setup-storage        # once per install, grants storage access
  mkdir -p ~/$DEVICE_REL_HOME
  cp $SDCARD_DIR/$FILE_NAME ~/$DEVICE_REL_HOME/
  sha256sum ~/$DEVICE_REL_HOME/$FILE_NAME

The printed hash MUST equal:
  $EXPECTED_SHA

If it differs, do not proceed — rerun this script.
EOF
else
    echo
    echo "-- Route B: scp over Termux sshd --"
    DEVICE_PATH="\$HOME/$DEVICE_REL_HOME/$FILE_NAME"
    run ssh "$SCP_TARGET" "mkdir -p \$HOME/$DEVICE_REL_HOME"
    run scp "$SRC" "$SCP_TARGET:$DEVICE_PATH"
    echo
    echo "Verifying hash on device..."
    REMOTE_SHA="$(ssh "$SCP_TARGET" "sha256sum $DEVICE_PATH" | awk '{print $1}')"
    echo "device reports: $REMOTE_SHA"
    if [ "$REMOTE_SHA" != "$EXPECTED_SHA" ]; then
        echo "TRANSFER FAILED: hash mismatch on device" >&2
        exit 1
    fi
    echo "TRANSFER VERIFIED."
    echo
    echo "Next on the phone (docs/11 Part B): launch llama-server against:"
    echo "  ~/$DEVICE_REL_HOME/$FILE_NAME"
fi
