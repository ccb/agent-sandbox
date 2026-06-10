#!/usr/bin/env bash
# PostToolUse launcher: run the renderer-coverage guard with whatever Python
# is available.
#
# We can't hard-code "$repo/venv/bin/python": anyone on conda (or any non-venv
# interpreter) -- e.g. the lab machines -- has no venv/, so that path errors on
# every edit. So we resolve an interpreter the same way format.sh resolves
# black: prefer the project venv, then fall back to PATH python3 / python. The
# coverage script puts the repo root on sys.path itself and only needs the
# stdlib, so any Python 3 works; if none is found we no-op rather than block.
#
# stdin (the PostToolUse hook JSON) is forwarded to the script unchanged.

set -euo pipefail

# Repo root = two levels up from this script (.claude/hooks/run_renderer_coverage.sh).
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
coverage_script="$script_dir/check_renderer_coverage.py"

# Prefer the project venv's python; fall back to whatever is on PATH.
if [[ -x "$repo_root/venv/bin/python" ]]; then
    python_bin="$repo_root/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
elif command -v python >/dev/null 2>&1; then
    python_bin="python"
else
    # No Python available -- don't block the edit.
    exit 0
fi

# The script's own exit code (2 on a coverage gap) is what we propagate.
exec "$python_bin" "$coverage_script"
