#!/usr/bin/env bash
# PostToolUse hook: silently format an edited .py file with black.
#
# Claude Code pipes the tool-call JSON to stdin; we pull out
# .tool_input.file_path. If it's a .py file that exists, we run black on it
# quietly. Anything else (.md, .ipynb, deletions) is a no-op. We only emit
# output if black itself errors, so a normal edit stays silent.

set -euo pipefail

# Repo root = two levels up from this script (.claude/hooks/format.sh).
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

# Pull tool_input.file_path out of the hook JSON without needing jq.
file_path="$(python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print(data.get("tool_input", {}).get("file_path", ""))
' || true)"

# Only format existing Python files.
[[ "$file_path" == *.py ]] || exit 0
[[ -f "$file_path" ]] || exit 0

# Prefer the project venv's black; fall back to whatever is on PATH. We default
# to uv's .venv/ but still honor a legacy venv/ for anyone who hasn't switched.
if [[ -x "$repo_root/.venv/bin/black" ]]; then
    black_bin="$repo_root/.venv/bin/black"
elif [[ -x "$repo_root/venv/bin/black" ]]; then
    black_bin="$repo_root/venv/bin/black"
elif command -v black >/dev/null 2>&1; then
    black_bin="black"
else
    # No black available — don't block the edit.
    exit 0
fi

if ! "$black_bin" -q "$file_path" 2>/tmp/agent-sandbox-black-err; then
    echo "auto-format hook: black failed on $file_path" >&2
    cat /tmp/agent-sandbox-black-err >&2
    rm -f /tmp/agent-sandbox-black-err
    # Exit 0 anyway so a formatting hiccup never blocks the edit.
    exit 0
fi
rm -f /tmp/agent-sandbox-black-err
exit 0
