#!/bin/bash
# Build llama.cpp binaries for all target architectures
# Usage: ./scripts/build-runtime.sh [arch]
#   No args = build all architectures
#   arch = build specific arch (arm, aarch64, x86_64)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/.build/releases"
DOCKERFILE="$SCRIPT_DIR/Dockerfile.cross"
IMAGE_NAME="ruach-llama-builder"

# Architectures to build
ARCHS="${1:-arm aarch64 x86_64}"

# llama.cpp version to build
LLAMA_VERSION="${LLAMA_CPP_VERSION:-b4550}"

mkdir -p "$OUTPUT_DIR"

echo "╔══════════════════════════════════════════╗"
echo "║  RUACH — llama.cpp Cross-Compilation     ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Version: $LLAMA_VERSION"
echo "║  Targets: $ARCHS"
echo "╚══════════════════════════════════════════╝"
echo ""

# Build Docker image
echo "Building Docker image..."
docker build \
  --build-arg LLAMA_CPP_VERSION="$LLAMA_VERSION" \
  -t "$IMAGE_NAME" \
  -f "$DOCKERFILE" \
  "$SCRIPT_DIR"

# Build for each architecture
for ARCH in $ARCHS; do
  echo ""
  echo "── Building for $ARCH ──────────────────────"
  
  docker run --rm \
    --build-arg TARGET_ARCH="$ARCH" \
    -v "$OUTPUT_DIR:/output" \
    "$IMAGE_NAME" \
    bash -c "cd /build/llama.cpp && \
      case '$ARCH' in \
        arm) \
          cmake -B build \
            -DCMAKE_SYSTEM_NAME=Linux \
            -DCMAKE_SYSTEM_PROCESSOR=armv7l \
            -DCMAKE_C_COMPILER=arm-linux-gnueabihf-gcc \
            -DCMAKE_CXX_COMPILER=arm-linux-gnueabihf-g++ \
            -DCMAKE_BUILD_TYPE=Release \
            -DLLAMA_CURL=OFF \
            -DGGML_NATIVE=OFF && \
          cmake --build build --config Release -j\$(nproc) && \
          cp build/bin/llama-server /output/llama-server-arm-linux && \
          ;; \
        aarch64) \
          cmake -B build \
            -DCMAKE_SYSTEM_NAME=Linux \
            -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
            -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc \
            -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ \
            -DCMAKE_BUILD_TYPE=Release \
            -DLLAMA_CURL=OFF \
            -DGGML_NATIVE=OFF && \
          cmake --build build --config Release -j\$(nproc) && \
          cp build/bin/llama-server /output/llama-server-aarch64-linux && \
          ;; \
        x86_64) \
          cmake -B build \
            -DCMAKE_BUILD_TYPE=Release \
            -DLLAMA_CURL=OFF \
            -DGGML_NATIVE=ON && \
          cmake --build build --config Release -j\$(nproc) && \
          cp build/bin/llama-server /output/llama-server-x86_64-linux && \
          ;; \
      esac"
  
  echo "✓ $ARCH built"
done

# Package as tar.gz
echo ""
echo "── Packaging ───────────────────────────────"
for ARCH in $ARCHS; do
  BIN="$OUTPUT_DIR/llama-server-${ARCH}-linux"
  TAR="$OUTPUT_DIR/llama-server-${ARCH}-linux.tar.gz"
  
  if [ -f "$BIN" ]; then
    cd "$OUTPUT_DIR"
    tar -czf "$TAR" "$(basename "$BIN")"
    echo "✓ $TAR"
  else
    echo "✗ $BIN not found"
  fi
done

echo ""
echo "── Done ────────────────────────────────────"
echo "Binaries in: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"/*.tar.gz 2>/dev/null || echo "No tar.gz files found"
