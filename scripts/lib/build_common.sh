#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Shared Build Helper & Environment Library
# ═══════════════════════════════════════════════════════

get_python() {
    if [ -x "venv/bin/python" ]; then
        printf '%s\n' "venv/bin/python"
    elif [ -x ".venv/bin/python" ]; then
        printf '%s\n' ".venv/bin/python"
    else
        printf '%s\n' "python3"
    fi
}

get_version() {
    local version=""
    local py_bin
    py_bin="$(get_python)"

    if [ -f "core/config.py" ]; then
        version=$(
            "$py_bin" - <<'PY' 2>/dev/null || true
import re

try:
    with open("core/config.py", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'APP_VERSION\s*=\s*["\']v?([0-9]+\.[0-9]+\.[0-9]+)', text)
    if m:
        print(m.group(1))
except Exception:
    pass
PY
        )
    fi

    if [ -z "$version" ] && [ -f "pyproject.toml" ]; then
        version=$(
            "$py_bin" - <<'PY' 2>/dev/null || true
import re

try:
    with open("pyproject.toml", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'version\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+)', text)
    if m:
        print(m.group(1))
except Exception:
    pass
PY
        )
    fi

    if [ -z "$version" ] && [ -f "README.md" ]; then
        version=$( (grep -oP 'version-v\K[0-9]+\.[0-9]+\.[0-9]+' README.md 2>/dev/null || true) | head -1 )
    fi

    if [ -z "$version" ]; then
        echo "❌ Unable to determine application version from core/config.py, pyproject.toml, or README.md." >&2
        return 1
    fi

    printf '%s\n' "$version"
}
