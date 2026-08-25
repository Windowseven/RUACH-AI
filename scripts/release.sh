#!/bin/bash
# Create a GitHub release with pre-built binaries
# Usage: ./scripts/release.sh <version>
# Example: ./scripts/release.sh 0.5.0

set -euo pipefail

VERSION="${1:?Usage: ./scripts/release.sh <version>}"
TAG="v$VERSION"
RELEASE_DIR=".build/releases"

echo "╔══════════════════════════════════════════╗"
echo "║  RUACH Release: $TAG"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check binaries exist
echo "Checking binaries..."
MISSING=0
for ARCH in arm aarch64 x86_64; do
  BIN="$RELEASE_DIR/llama-server-${ARCH}-linux"
  TAR="$RELEASE_DIR/llama-server-${ARCH}-linux.tar.gz"
  if [ -f "$TAR" ]; then
    echo "  ✓ $TAR ($(du -h "$TAR" | cut -f1))"
  elif [ -f "$BIN" ]; then
    echo "  ⚠ $BIN found but not packaged. Packaging now..."
    cd "$RELEASE_DIR"
    tar -czf "llama-server-${ARCH}-linux.tar.gz" "$(basename "$BIN")"
    cd - > /dev/null
    echo "  ✓ Packaged"
  else
    echo "  ✗ $BIN not found"
    MISSING=1
  fi
done

if [ "$MISSING" -eq 1 ]; then
  echo ""
  echo "Missing binaries. Run ./scripts/build-runtime.sh first."
  exit 1
fi

# Create git tag
echo ""
echo "Creating git tag $TAG..."
git tag -a "$TAG" -m "Release $TAG"
git push origin "$TAG"

# Create GitHub release
echo ""
echo "Creating GitHub release..."
gh release create "$TAG" \
  --title "RUACH $TAG" \
  --notes "## RUACH AI $TAG

### Pre-built llama.cpp binaries
- \`llama-server-aarch64-linux.tar.gz\` — ARM 64-bit (Termux on modern phones)
- \`llama-server-x86_64-linux.tar.gz\` — x86_64 (laptops, servers)

### Install
\`\`\`bash
git clone https://github.com/Windowseven/RUACH-AI.git
cd RUACH-AI
npm install
ruach start
\`\`\`" \
  "$RELEASE_DIR"/llama-server-*.tar.gz

echo ""
echo "✓ Release $TAG created!"
echo "  https://github.com/furahamogela/RUACH-AI/releases/tag/$TAG"
