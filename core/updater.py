import os
import sys
import json
import shlex
import platform
import urllib.request
from typing import Optional

from packaging.version import Version, InvalidVersion
from core.config import GITHUB_API_LATEST_RELEASE


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _parse_version(tag: str) -> Optional[Version]:
    """Strip leading 'v' and return a packaging.Version, or None on failure."""
    try:
        return Version(tag.lstrip("v"))
    except InvalidVersion:
        return None


def _current_arch_tokens() -> list[str]:
    """
    Returns a list of architecture tokens commonly used in filenames for the
    current machine.
    """
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return ["x86_64", "amd64"]
    if machine in ("arm64", "aarch64"):
        return ["arm64", "aarch64", "arm64-v8a"]
    return [machine]


# ─────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────

def check_for_updates(current_version: str) -> Optional[dict]:
    """
    Checks GitHub API for the latest release.

    Returns a dict with 'version', 'body', 'assets' **only** when the remote
    tag is *strictly newer* than current_version (semantic comparison via
    packaging.version).  Returns None otherwise.
    """
    current = _parse_version(current_version)
    if current is None:
        print(f"[Updater] Cannot parse current version '{current_version}' — skipping update check.")
        return None

    try:
        req = urllib.request.Request(
            GITHUB_API_LATEST_RELEASE,
            headers={"User-Agent": "DotGhostBoard-Updater"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                latest_tag = data.get("tag_name", "").strip()
                latest = _parse_version(latest_tag)

                # FIX #2 — only update when remote is STRICTLY greater
                if latest and latest > current:
                    return {
                        "version": latest_tag,
                        "body": data.get("body", "No release notes provided."),
                        "assets": data.get("assets", []),
                    }
    except Exception as e:
        print(f"[Updater] Failed to check for updates: {e}")

    return None


def identify_platform_asset(
    assets: list[dict],
    *,
    strict_arch: bool = False,
) -> Optional[str]:
    """
    Returns the best download URL for this platform/architecture.

    Parameters
    ----------
    assets : list[dict]
        Asset list from the GitHub release payload.
    strict_arch : bool
        If True,  only return a URL whose filename contains the current
        architecture token (e.g. 'x86_64').  If False (default), fall back
        to the first type-matching asset when no arch-specific one is found.
    """
    is_appimage = bool(os.environ.get("APPIMAGE"))
    arch_tokens = _current_arch_tokens()

    def _arch_match(name: str) -> bool:
        """True when the asset name contains any of the running machine's arch tokens."""
        name_lower = name.lower()
        return any(t in name_lower for t in arch_tokens)

    def _pick(candidates: list[str]) -> Optional[str]:
        """Prefer arch-matching URL; fall back if strict_arch is False."""
        arch_hits = [u for u in candidates if _arch_match(os.path.basename(u))]
        if arch_hits:
            return arch_hits[0]
        if not strict_arch:
            return candidates[0] if candidates else None
        return None

    candidates: list[str] = []

    for asset in assets:
        name = asset.get("name", "").lower()
        url  = asset.get("browser_download_url")
        if not url:
            continue

        if sys.platform == "linux":
            if is_appimage and name.endswith(".appimage"):
                candidates.append(url)
            elif not is_appimage and name.endswith(".deb"):
                candidates.append(url)

        elif sys.platform == "win32":
            if name.endswith(".exe") or name.endswith(".msi"):
                candidates.append(url)

        elif sys.platform == "darwin":
            if name.endswith(".dmg"):
                candidates.append(url)

    return _pick(candidates)


def download_update(url: str, output_path: str, progress_callback=None):
    """
    Downloads the asset from *url* to *output_path*.

    Calls ``progress_callback(percentage: int)`` periodically if supplied.
    Raises ``RuntimeError`` on network / I/O problems so callers can surface
    a meaningful error instead of silently writing a corrupt file.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DotGhostBoard-Updater"},
    )
    try:                                   # FIX #4 — robust error handling
        with urllib.request.urlopen(req, timeout=30) as response:
            total_size  = int(response.getheader("Content-Length", 0))
            chunk_size  = 8192
            downloaded  = 0

            with open(output_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and progress_callback:
                        percent = int((downloaded / total_size) * 100)
                        progress_callback(percent)

    except urllib.error.URLError as exc:
        raise RuntimeError(f"[Updater] Network error during download: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"[Updater] I/O error writing '{output_path}': {exc}") from exc


def apply_update(downloaded_file: str, asset_url: str):
    """
    Installs / launches the downloaded update appropriate for this platform.
    """
    import stat
    import subprocess
    import shutil
    import tempfile

    ext = os.path.splitext(downloaded_file)[1].lower()

    # ── AppImage ────────────────────────────────────────────────────────────
    if ext == ".appimage" or asset_url.lower().endswith(".appimage"):
        current_appimage = os.environ.get("APPIMAGE")
        if not current_appimage:
            raise RuntimeError("Cannot apply AppImage update: $APPIMAGE env var is missing.")

        old_file = current_appimage + ".old"
        if os.path.exists(old_file):
            try:
                os.remove(old_file)
            except OSError:
                pass

        # Avoid "Text file busy" — rename before overwriting
        os.rename(current_appimage, old_file)
        shutil.move(downloaded_file, current_appimage)

        st = os.stat(current_appimage)
        os.chmod(current_appimage, st.st_mode | stat.S_IEXEC)

        print("[Updater] Restarting AppImage…")
        # FIX #1 — os.execle requires an explicit env and is error-prone;
        #           os.execv reuses the current environment, which is correct.
        os.execv(current_appimage, [current_appimage] + sys.argv[1:])
        # execv replaces the process — code below this line is never reached.

    # ── DEB ─────────────────────────────────────────────────────────────────
    elif ext == ".deb" or asset_url.lower().endswith(".deb"):
        print(f"[Updater] Installing DEB via pkexec: {downloaded_file}")

        # FIX #3 — shlex.quote prevents shell-injection and handles paths
        #           that contain spaces or special characters.
        safe_path   = shlex.quote(downloaded_file)
        script_path = os.path.join(tempfile.gettempdir(), "dotghostboard_install.sh")

        with open(script_path, "w") as f:
            f.write(f"#!/bin/sh\ndpkg -i {safe_path}\n")

        os.chmod(script_path, 0o755)
        subprocess.Popen(["pkexec", script_path])

    # ── Windows installer ───────────────────────────────────────────────────
    elif ext in (".exe", ".msi"):
        print(f"[Updater] Running Windows installer: {downloaded_file}")
        subprocess.Popen([downloaded_file])
        sys.exit(0)

    # ── macOS DMG ───────────────────────────────────────────────────────────
    elif ext == ".dmg":
        if sys.platform == "darwin":
            subprocess.Popen(["open", downloaded_file])

    # ── Fallback — open containing directory ────────────────────────────────
    else:
        if sys.platform == "linux":
            subprocess.Popen(["xdg-open", os.path.dirname(downloaded_file)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", downloaded_file])