#!/usr/bin/env python3
"""Refresh PROGRESS.md's in-flight table from live GitHub state.

This is a Claude Code PostToolUse hook (see .claude/settings.json). It fires
after every Bash tool call, but only does work when the command was a
`git commit` -- the natural moment for the progress tracker to drift. On any
other command it exits immediately.

What it updates, and what it leaves alone:

  * For each row in the "In flight" table that links a PR (``.../pull/N``), it
    looks up that PR's current state on GitHub and rewrites *only* the Status
    cell -- ready to merge / needs conflict resolution / in design / merged.
  * It re-stamps the "Last synced with GitHub on **YYYY-MM-DD**" line.

Everything else is hand-curated -- titles, owners, which items are listed, the
design-doc rows, the backlog, the Shipped section -- so the hook never touches
it. A PR that has merged is flagged (not auto-moved) so a human moves the row
to Shipped on purpose.

It is deliberately defensive: if `gh` is missing, the user is offline or
unauthenticated, or PROGRESS.md isn't there, it simply no-ops. It never blocks
the commit (always exits 0) and only writes PROGRESS.md when something changed.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

# Repo root = two levels up from this script (.claude/hooks/update_progress.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
PROGRESS = REPO_ROOT / "PROGRESS.md"

# Matches the PR number in an in-flight Item cell, e.g. ".../pull/64".
PR_LINK = re.compile(r"/pull/(\d+)")
# Matches the bold date in the maintenance footer.
SYNCED_LINE = re.compile(r"(Last synced with GitHub on \*\*)\d{4}-\d{2}-\d{2}(\*\*)")


def status_for(pr: dict) -> str:
    """Map a PR's GitHub state to the Status label used in the table."""
    state = pr.get("state")
    if state == "MERGED":
        return "✅ Merged — move to Shipped"
    if state == "CLOSED":
        return "⚪ Closed — move/remove"
    if pr.get("isDraft"):
        return "🔵 In design (draft PR)"
    mergeable = pr.get("mergeable")
    if mergeable == "CONFLICTING":
        return "🟠 Needs conflict resolution"
    if mergeable == "MERGEABLE":
        return "🟢 Ready to merge"
    # UNKNOWN: GitHub hasn't finished computing the merge state yet.
    return "🟠 Mergeability unverified"


def gh_json(args: list[str]) -> object | None:
    """Run a `gh` command and parse its JSON output, or None on any failure."""
    try:
        out = subprocess.run(
            ["gh", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def pr_states(numbers: set[int]) -> dict[int, dict]:
    """Look up the current state of each PR number referenced in the table."""
    fields = "number,state,isDraft,mergeable"
    states: dict[int, dict] = {}

    # One list call covers every open PR cheaply.
    open_prs = gh_json(
        ["pr", "list", "--state", "open", "--json", fields, "--limit", "100"]
    )
    if isinstance(open_prs, list):
        for pr in open_prs:
            states[pr["number"]] = pr

    # Any referenced PR not in the open set has merged or closed -- look those
    # up individually (there are usually only a handful).
    for n in numbers - states.keys():
        pr = gh_json(["pr", "view", str(n), "--json", fields])
        if isinstance(pr, dict):
            states[n] = pr

    return states


def is_git_commit(command: str) -> bool:
    """True if the Bash command ran (or chained) a `git commit`."""
    # Tolerate leading flags/paths: match `git ... commit` in any segment.
    return bool(re.search(r"\bgit\b[^\n&|;]*\bcommit\b", command))


def main() -> int:
    # The hook JSON arrives on stdin. Only act on `git commit` commands.
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not is_git_commit(command):
        return 0

    if not PROGRESS.is_file():
        return 0
    text = PROGRESS.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Collect every PR number the in-flight table references.
    numbers = {int(m.group(1)) for line in lines for m in PR_LINK.finditer(line)}
    if not numbers:
        return 0

    states = pr_states(numbers)
    if not states:
        # No reachable GitHub data (offline / unauthenticated / no gh) -> no-op.
        return 0

    changed = False
    for i, line in enumerate(lines):
        if not line.startswith("| "):
            continue
        m = PR_LINK.search(line)
        if not m:
            continue
        pr = states.get(int(m.group(1)))
        if not pr:
            continue
        cells = line.split("|")
        # cells[1] is the Status column (cells[0] is the empty pre-pipe field).
        if len(cells) < 3:
            continue
        new_status = status_for(pr)
        if cells[1].strip() != new_status:
            cells[1] = f" {new_status} "
            lines[i] = "|".join(cells)
            changed = True

    # Re-stamp the synced date (in real local time -- this is a normal script,
    # not the sandboxed Workflow runtime).
    today = datetime.date.today().isoformat()
    new_text = "".join(lines)
    stamped, n = SYNCED_LINE.subn(rf"\g<1>{today}\g<2>", new_text)
    if n and stamped != new_text:
        new_text = stamped
        changed = True

    if changed:
        PROGRESS.write_text(new_text, encoding="utf-8")
        print(
            f"update_progress: refreshed PROGRESS.md from GitHub ({today}).",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
