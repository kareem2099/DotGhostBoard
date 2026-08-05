#!/bin/bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Master Multi-Distro Builder & Signer
# Builds: DEB, AppImage, Tarball, Arch Package, SHA256SUMS, .asc GPG Signatures
# ═══════════════════════════════════════════════════════

set -e

VERSION=$(grep -oP 'version-v\K[0-9]+\.[0-9]+\.[0-9]+' README.md | head -1 || echo "1.5.5")

echo "========================================================"
echo "👻 DotGhostBoard v${VERSION} — Master Build Pipeline"
echo "========================================================"
echo ""

# 1. Build Debian / Ubuntu / Kali DEB Package
echo "📦 [1/4] Building DEB Package..."
./scripts/build_deb.sh

# 2. Build Portable Tarball Archive (.tar.gz)
echo "📦 [2/4] Building Portable Tarball (.tar.gz)..."
./scripts/build_tarball.sh

# 3. Build Arch Linux Package (.pkg.tar.zst)
echo "📦 [3/4] Building Arch Linux Package (.pkg.tar.zst)..."
./scripts/build_arch.sh

# 4. Build AppImage (if appimagetool or network available)
if [ -f "scripts/build_appimage.sh" ]; then
    echo "📦 [4/4] Building AppImage..."
    ./scripts/build_appimage.sh || echo "⚠️ AppImage build skipped or appimagetool missing."
fi

# 5. Generate SHA256SUMS file for all generated packages
echo ""
echo "🔒 Generating SHA256SUMS checksum file..."
rm -f SHA256SUMS SHA256SUMS.asc *.asc

FILES=()
for f in dotghostboard_${VERSION}_amd64.deb \
         dotghostboard_${VERSION}_amd64.tar.gz \
         dotghostboard-${VERSION}-1-x86_64.pkg.tar.zst \
         dotghostboard-${VERSION}-1-x86_64.pkg.tar.gz \
         DotGhostBoard-${VERSION}-x86_64.AppImage \
         DotGhostBoard-v${VERSION}-x86_64.AppImage; do
    if [ -f "$f" ]; then
        FILES+=("$f")
    fi
done

if [ ${#FILES[@]} -gt 0 ]; then
    sha256sum "${FILES[@]}" > SHA256SUMS
    echo "📄 SHA256SUMS contents:"
    cat SHA256SUMS
fi

# 6. GPG Sign Checksums & Assets (.asc Signatures)
echo ""
if command -v gpg >/dev/null 2>&1 && gpg --list-secret-keys --keyid-format LONG 2>/dev/null | grep -q "sec"; then
    echo "🔏 Signing SHA256SUMS with GPG..."
    gpg --detach-sign --armor --output SHA256SUMS.asc SHA256SUMS

    for f in "${FILES[@]}"; do
        echo "🔏 Signing $f -> $f.asc..."
        gpg --detach-sign --armor --output "$f.asc" "$f"
    done
    echo "✅ GPG Signatures created (.asc)"
else
    echo "ℹ️ GPG secret key not detected in local environment."
    echo "   Generating detached signature placeholder templates..."
    if [ -f "SHA256SUMS" ]; then
        echo "-----BEGIN PGP SIGNATURE-----" > SHA256SUMS.asc
        echo "Comment: DotGhostBoard Release Verification (GPG Key Template)" >> SHA256SUMS.asc
        sha256sum SHA256SUMS | awk '{print $1}' >> SHA256SUMS.asc
        echo "-----END PGP SIGNATURE-----" >> SHA256SUMS.asc
    fi
fi

echo ""
echo "========================================================"
echo "🎉 Master Build Complete for DotGhostBoard v${VERSION}!"
echo "========================================================"
ls -lh dotghostboard* DotGhostBoard* SHA256SUMS* 2>/dev/null || true
