# Research journals

A lightweight daily log so the whole team (and Chris) can see what everyone is
working on. Think lab notebook, not polished writeup — a few honest lines a day
is perfect.

## How it works

- **One file per person**, named `journal/<firstname>.md` (e.g. `journal/alistair.md`).
- **Add a dated entry each day you work**, with the **newest entry at the top**.
- Keep it short. Link issues and PRs with `#` (e.g. `#3`, `#13`) so they
  auto-link on GitHub.
- Commit your journal alongside your other work, or in its own small commit —
  whatever's natural. It's fine to push journal updates straight to `main`.

This isn't busywork: it's how we keep each other unblocked and how Chris stays in
the loop without interrupting you. Write blockers down — that's often where you'll
get the fastest help.

## Daily entry template

Copy this block to the top of your file each working day and fill it in:

```markdown
## YYYY-MM-DD

**Focus:** <the issue/topic you're on, e.g. #4 Reflect step>

**Done today:**
- ...

**Blockers / questions:**
- ... (write "none" if none)

**Next:**
- ...
```

Keep entries in reverse-chronological order (today on top, scroll down for
history). Don't delete old entries — the history is the point.

## Design notes vs. journals

Journals are for **daily logs**. If you write up a larger **design proposal**
(architecture, a new subsystem), that belongs in `docs/design/` as its own
document — not in your journal — so it's easy to find and review. Mention it in
your journal and link to it.
