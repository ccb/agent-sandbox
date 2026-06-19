#!/usr/bin/env bash
# Manual launcher: resync PROGRESS.md's in-flight table with GitHub.
#
# Run it by hand -- `.claude/hooks/update_progress.sh` -- when you want the
# tracker refreshed. It is no longer wired as a PostToolUse hook, so it only
# runs when called.
#
# Like run_renderer_coverage.sh, we can't hard-code "$repo/venv/bin/python":
# anyone on conda or a bare interpreter (e.g. the lab machines) has no venv/.
# So we resolve an interpreter the same way -- prefer the project venv, then
# fall back to PATH python3 / python. The updater only needs the stdlib plus
# the `gh` CLI, and no-ops cleanly if either is missing.

set -euo pipefail

# Repo root = two levels up from this script (.claude/hooks/update_progress.sh).
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
updater="$script_dir/update_progress.py"

# Prefer the project venv's python; fall back to whatever is on PATH.
if [[ -x "$repo_root/venv/bin/python" ]]; then
    python_bin="$repo_root/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
elif command -v python >/dev/null 2>&1; then
    python_bin="python"
else
    # No Python available -- don't block the commit.
    exit 0
fi

# The updater always exits 0 (it never blocks a commit), so this is safe.
exec "$python_bin" "$updater"
