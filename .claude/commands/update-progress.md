---
description: Resync PROGRESS.md's in-flight table with live GitHub state
---

`/update-progress` refreshes the in-flight table in `PROGRESS.md` from live
GitHub issue/PR state by running the project's progress updater.

This command is **invoked on demand only** — it is **not** a hook and does
nothing automatically. The auto-sync PostToolUse hook was removed
(commit `9af8624`), so the tracker only refreshes when you run this command.

Run, from the repo root:

```
.claude/hooks/update_progress.sh
```

(The script resolves an interpreter itself — project `venv/`, else `python3` /
`python` on PATH — and only needs the stdlib plus the `gh` CLI. It always exits
0 and **no-ops cleanly** if `gh` or Python is missing, or if `PROGRESS.md` is
absent. Run by hand like this, it skips the old `git commit` self-gate and just
syncs.)

Then report what changed: show `git diff --stat PROGRESS.md` (or say the file
was unchanged). If the script no-op'd because `gh`/Python was unavailable, say
so plainly. Do not commit or push — leave the edited `PROGRESS.md` for review.
