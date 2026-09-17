import os
import sys
import json
import shlex
import platform
import urllib.request
from typing import Optional, Literal

from packaging.version import Version, InvalidVersion
from core.config import GITHUB_API_RELEASES

# ─────────────────────────────────────────────
#  Channel type
# ─────────────────────────────────────────────

Channel = Literal["stable", "beta", "alpha"]

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _parse_version(tag: str) -> Optional[Version]:
    """
    Strip leading 'v', normalize dash-style pre-release suffixes to PEP 440,
    and return a packaging.Version, or None on failure.

    Examples
    --------
    v2.0.0-beta.2  → 2.0.0b2
    v2.0.0-rc.1    → 2.0.0rc1
    v2.0.0-alpha.1 → 2.0.0a1
    v2.0.0         → 2.0.0
    """
    import re
    normalized = tag.lstrip("v")
    # Normalize  -alpha.N / -beta.N / -rc.N  → aN / bN / rcN
    normalized = re.sub(r"-alpha\.(\d+)$", r"a\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"-beta\.(\d+)$",  r"b\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"-rc\.(\d+)$",    r"rc\1", normalized, flags=re.IGNORECASE)
    try:
        return Version(normalized)
    except InvalidVersion:
        return None


def _classify_release(version: Version) -> str:
    """
    Classify a release version into one of four buckets:
      'stable' — no pre-release segment
      'rc'     — release candidate  (e.g. 2.0.0rc1, 2.0.0-rc.1)
      'beta'   — beta release       (e.g. 2.0.0b1,  2.0.0-beta.1)
      'alpha'  — alpha release      (e.g. 2.0.0a1,  2.0.0-alpha.1)
    """
    if not version.is_prerelease:
        return "stable"
    pre_type = version.pre[0] if version.pre else ""
    if pre_type == "rc":
        return "rc"
    if pre_type == "b":
        return "beta"
    if pre_type == "a":
        return "alpha"
    return "stable"  # fallback — treat unknown pre-release as stable


def _release_matches_channel(release_type: str, channel: Channel) -> bool:
    """
    Return True when a release of *release_type* should be visible
    to a user on the given *channel*.

      Stable → stable only
      Beta   → stable, beta, rc
      Alpha  → stable, beta, rc, alpha
    """
    if channel == "stable":
        return release_type == "stable"
    if channel == "beta":
        return release_type in ("stable", "beta", "rc")
    if channel == "alpha":
        return True  # accepts all
    return release_type == "stable"


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

def check_for_updates(
    current_version: str,
    channel: Channel = "stable",
) -> Optional[dict]:
    """
    Checks GitHub API for the best available release for *channel*.

    Algorithm (unified across all channels):
      1. Fetch /releases list
      2. Parse each tag — silently skip invalid ones
      3. Filter by channel (stable/beta/alpha visibility rules)
      4. Discard candidates ≤ current_version  (no downgrade)
      5. Return the newest candidate's info dict, or None

    Returns a dict with 'version', 'body', 'assets' only when a
    strictly-newer, channel-appropriate release exists.
    """
    current = _parse_version(current_version)
    if current is None:
        print(
            f"[Updater] Cannot parse current version '{current_version}'"
            " — skipping update check."
        )
        return None

    try:
        req = urllib.request.Request(
            GITHUB_API_RELEASES,
            headers={"User-Agent": "DotGhostBoard-Updater"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                return None
            releases = json.loads(response.read().decode())
    except Exception as e:
        print(f"[Updater] Failed to fetch releases: {e}")
        return None

    best_version: Optional[Version] = None
    best_release: Optional[dict]    = None

    for release in releases:
        tag = release.get("tag_name", "").strip()
        v   = _parse_version(tag)
        if v is None:
            continue  # silently ignore unparseable tags

        release_type = _classify_release(v)
        if not _release_matches_channel(release_type, channel):
            continue  # not visible on this channel

        if v <= current:
            continue  # no downgrade, and no same-version noise

        if best_version is None or v > best_version:
            best_version = v
            best_release = release

    if best_release is None:
        return None

    return {
        "version": best_release.get("tag_name", ""),
        "body":    best_release.get("body", "No release notes provided."),
        "assets":  best_release.get("assets", []),
    }


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
        script_dir = os.path.expanduser("~/.local/share/dotghostboard/updates")
        os.makedirs(script_dir, exist_ok=True)
        script_path = os.path.join(script_dir, "dotghostboard_install.sh")

        with open(script_path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write(f"dpkg -i {safe_path}\n")
            f.write(f"rm -f {safe_path}\n")
            f.write("rm -f \"$0\"\n")

        os.chmod(script_path, 0o755)
        
        try:
            subprocess.Popen(["pkexec", script_path])
        except Exception as e:
            print(f"[Updater] Failed to execute update script: {e}")

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