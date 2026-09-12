#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Master Multi-Distro Builder & Signer
# Builds: DEB, AppImage, Tarball, Arch Package, SHA256SUMS, .asc GPG Signatures
# ═══════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

source "$SCRIPT_DIR/lib/build_common.sh"

VERSION="$(get_version)"
GPG_KEY_ID="${GPG_KEY_ID:-48E2D66B9B738A1D24DE5B2FD3EB5327471C8F22}"

echo "========================================================"
echo "👻 DotGhostBoard v${VERSION} — Master Build Pipeline"
echo "========================================================"
echo ""

echo "🧹 Cleaning previous release artifacts..."
rm -f \
    "dotghostboard_${VERSION}_amd64.deb" \
    "dotghostboard_${VERSION}_amd64.tar.gz" \
    "dotghostboard-${VERSION}-1-x86_64.pkg.tar.zst" \
    "dotghostboard-${VERSION}-1-x86_64.pkg.tar.gz" \
    "DotGhostBoard-${VERSION}-x86_64.AppImage" \
    "DotGhostBoard-v${VERSION}-x86_64.AppImage"
rm -f SHA256SUMS SHA256SUMS.asc

# 0. Build shared compiled binary ONCE
echo "🚀 [0/4] Compiling shared binary..."
bash "$SCRIPT_DIR/build_binary.sh"

# 1. Build Debian / Ubuntu / Kali DEB Package
echo ""
echo "📦 [1/4] Building DEB Package..."
bash "$SCRIPT_DIR/build_deb.sh"

# 2. Build Portable Tarball Archive (.tar.gz)
echo ""
echo "📦 [2/4] Building Portable Tarball (.tar.gz)..."
bash "$SCRIPT_DIR/build_tarball.sh"

# 3. Build Arch Linux Package (.pkg.tar.zst)
echo ""
echo "📦 [3/4] Building Arch Linux Package (.pkg.tar.zst)..."
bash "$SCRIPT_DIR/build_arch.sh"

# 4. Build AppImage (Strict Release Mode)
echo ""
echo "📦 [4/4] Building AppImage..."
bash "$SCRIPT_DIR/build_appimage.sh"

# 5. Validate that all required release artifacts exist
echo ""
echo "🔍 Validating generated release artifacts..."

require_file() {
    if [ ! -f "$1" ]; then
        echo "❌ Required release artifact missing: $1" >&2
        exit 1
    fi
}

require_file "dotghostboard_${VERSION}_amd64.deb"
require_file "dotghostboard_${VERSION}_amd64.tar.gz"
require_file "DotGhostBoard-${VERSION}-x86_64.AppImage"

if [ -f "dotghostboard-${VERSION}-1-x86_64.pkg.tar.zst" ]; then
    ARCH_FILE="dotghostboard-${VERSION}-1-x86_64.pkg.tar.zst"
elif [ -f "dotghostboard-${VERSION}-1-x86_64.pkg.tar.gz" ]; then
    ARCH_FILE="dotghostboard-${VERSION}-1-x86_64.pkg.tar.gz"
else
    echo "❌ Arch package was not produced." >&2
    exit 1
fi

FILES=(
    "dotghostboard_${VERSION}_amd64.deb"
    "dotghostboard_${VERSION}_amd64.tar.gz"
    "$ARCH_FILE"
    "DotGhostBoard-${VERSION}-x86_64.AppImage"
)

# 6. Generate SHA256SUMS file for official release packages
echo ""
echo "🔒 Generating SHA256SUMS checksum file..."

# Clean previous signatures for these specific files
for f in "${FILES[@]}"; do
    rm -f "${f}.asc"
done

sha256sum "${FILES[@]}" > SHA256SUMS
echo "📄 SHA256SUMS contents:"
cat SHA256SUMS

# 6. GPG Sign Checksums & Assets (.asc Signatures)
echo ""
if command -v gpg >/dev/null 2>&1 && gpg --list-secret-keys "$GPG_KEY_ID" &>/dev/null; then
    echo "🔏 Signing SHA256SUMS with GPG key ($GPG_KEY_ID)..."
    gpg --yes \
        --local-user "$GPG_KEY_ID" \
        --detach-sign \
        --armor \
        --output SHA256SUMS.asc \
        SHA256SUMS

    for f in "${FILES[@]}"; do
        echo "🔏 Signing $f -> $f.asc..."
        gpg --yes \
            --local-user "$GPG_KEY_ID" \
            --detach-sign \
            --armor \
            --output "$f.asc" \
            "$f"
    done
    echo "✅ GPG signatures created (.asc)"
else
    echo "ℹ️ No GPG secret key detected for $GPG_KEY_ID; signatures skipped."
fi

echo ""
echo "========================================================"
echo "🎉 Master Build Complete for DotGhostBoard v${VERSION}!"
echo "========================================================"
ls -lh dotghostboard* DotGhostBoard* SHA256SUMS* 2>/dev/null || true
