# Git & GitHub workflow

A practical how-to for this repo: the everyday git commands, branching, opening
a pull request (including picking exactly which files go in it), and opening
an issue. See [student-onboarding.md](student-onboarding.md) for the team's
overall workflow rules (small PRs, keep the suite green, stacked-PR order);
this doc is the command-level "how do I actually do that" reference.

## The core commands you'll use daily

| Command | What it does |
|---|---|
| `git status` | What's changed, staged vs. not. Run this constantly. |
| `git diff` | Line-by-line unstaged changes. `git diff --staged` for staged ones. |
| `git add <file>` | Stage a file for the next commit. |
| `git commit -m "message"` | Snapshot everything staged. |
| `git push` | Send your commits to GitHub. `git push -u origin <branch>` the first time on a new branch. |
| `git pull` | Fetch + merge the latest from your branch's remote. |
| `git log --oneline -10` | Recent commit history, one line each. |
| `git branch` | List local branches (`*` marks the current one). |
| `git switch <branch>` | Move to another branch. `git switch -c <branch>` creates + switches. |

The one habit that saves you the most grief: **run `git status` before and
after anything that touches history** (`checkout`, `restore`, `reset`,
`stash`). It tells you exactly what's about to move.

## Making a branch

Always branch off an up-to-date `main` — never commit directly to `main`
(the one exception is your own `journal/<name>.md`, which pushes straight
there, per onboarding).

```bash
git switch main
git pull
git switch -c my-feature-branch     # e.g. fix/sleep-gate-mismatch
```

Name it for the thing you're doing, not for yourself — `fix/...`,
`feature/...`, or just a short descriptive slug all work.

## Choosing exactly which files go into a commit (and PR)

A PR is just "everything different between your branch and `main`," built
from your commits — so controlling what's *in* a commit is how you control
what's in the PR. Two tools:

1. **Stage files explicitly, not everything.**
   ```bash
   git add path/to/file_a.py path/to/file_b.py
   ```
   Avoid `git add -A` / `git add .` when your working tree has unrelated
   changes sitting around — it's easy to accidentally sweep in a file you
   didn't mean to commit (or a secret/credential file). Check what actually
   got staged with `git status` before committing.

2. **Split unrelated changes into separate commits (or leave some out
   entirely).** If your working tree has both "the feature I want to ship"
   and "an unrelated fix I'm not ready to publish," stage and commit only the
   first set:
   ```bash
   git add feature_file.py feature_test.py
   git commit -m "Add the feature"
   # the unrelated fix stays uncommitted, or gets its own separate commit
   # on a separate branch later -- your choice, but don't mix them into one.
   ```
   Whatever you `git push` on your branch is what a PR from that branch will
   show — so a file you never staged/committed never appears in the PR,
   full stop.

## Opening a pull request

Once your commit(s) are ready:

```bash
git push -u origin my-feature-branch
gh pr create --base main --head my-feature-branch \
  --title "Short, specific title" \
  --body "$(cat <<'EOF'
## Summary
- What changed, and why -- one or two bullets.

## Test plan
- [x] `uv run pytest -q` -- all green
- [x] `uv run black --check .`
EOF
)"
```

No `gh`? Push, then open `https://github.com/ccb/agent-sandbox/pulls` — GitHub
shows a "Compare & pull request" banner for your just-pushed branch.

### This repo's PR body convention

Every PR in this repo follows roughly the same shape — write yours the same
way so reviewers know where to look:

- **`## Summary`** — a few bullets, each stating *what changed and why*, not
  a line-by-line narration of the diff. ("Removed X (dead code — never
  wired up)" beats "Deleted lines 40-52 of drives.py.")
- **`## Test plan`** — a checklist of what you actually ran, with the
  command and its result. `- [x] uv run pytest -q -- all green`, not just
  "tests pass."
- For a **bug-fix** PR, `## Problem` / `## Fix` / `## Verification` is the
  other common shape in this repo's history — `## Problem` states the bug
  and its user-visible impact, `## Fix` explains the change, `## Verification`
  is the same kind of test-plan checklist.
- Reference the issue it closes with `Closes #123` (GitHub auto-closes the
  issue when the PR merges) or just `#123` if it's related but doesn't fully
  close it.
- Keep the **title under ~70 characters** and specific — "Fix Sleep's
  disconnected tiredness threshold (#931)", not "Bug fix."

## Opening an issue

```bash
gh issue create --repo ccb/agent-sandbox \
  --title "Short, specific summary" \
  --body "What's wrong / what you want, how to reproduce or why it matters."
```

Or via the browser: `https://github.com/ccb/agent-sandbox/issues` → **New
issue**.

A good issue:
- **Title**: specific enough to search for later — "SleepPenn gates on an
  unreachable is_sleepy flag", not "bug".
- **Body**: for a bug, what's happening + what you expected + how to
  reproduce it (a failing test or exact command is ideal); for a feature,
  what you want and why.
- Link related issues/PRs with `#123` — GitHub auto-links them.

## Quick reference: the full loop

```bash
git switch main && git pull                  # start from a clean main
git switch -c fix/my-thing                   # branch
# ... make changes ...
git status                                   # check what changed
git add file1.py file2.py                    # stage only what belongs together
git commit -m "Fix the thing"                # snapshot
git push -u origin fix/my-thing               # publish the branch
gh pr create --base main --head fix/my-thing  --title "..." --body "..."
```
