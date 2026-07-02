# Student onboarding

Welcome to the group's summer research project! This is the practical "first
week" guide: how to get set up, how we work, and the one daily habit we ask of
everyone (the research journal). For *what* we're building and why, read the
[README](../README.md) first — this doc assumes it.

## Day one checklist

1. **Accept the GitHub invite.** You'll get an email, or find it at
   <https://github.com/ccb/agent-sandbox/invitations> (signed in as your GitHub
   account). You have **write** access — you can push branches and open PRs.
2. **Set up the project.** Follow [README → Setup](../README.md#setup). Short
   version, with [uv](https://docs.astral.sh/uv/):
   ```bash
   git clone https://github.com/ccb/agent-sandbox.git
   cd agent-sandbox
   uv sync --extra dev            # .venv/ + engine + pytest/black
   ```
3. **Confirm it's green** before you change anything — this is your sanity check
   that the environment is good:
   ```bash
   uv run pytest -q                # ~1300+ tests, should be all green
   ```
4. **Play a game** to feel the engine from the outside:
   ```bash
   uv run python -m text_adventure_games.adventures.tomb_of_nassak_an_rah
   ```
5. **Start your journal** (see below) — your first entry can just be "got set up,
   tests green, reading X."

## Read these, roughly in order

- [README.md](../README.md) — the project, the idea, the setup.
- [docs/game-development-guide.md](game-development-guide.md) — the engine's core
  classes and primitives (`Thing`/`Location`/`Item`/`Character`/`Action`/`Block`
  and friends). The best mental model for the codebase.
- [docs/reading-the-output.md](reading-the-output.md) — how to read what a game
  prints (channels, the renderer).
- [docs/TESTING.md](TESTING.md) — how we test, and what we expect of a PR.
- [docs/design/](design/) — design specs for larger subsystems (reactions,
  perception, the Smallville port, …). Skim the ones near your area; write one
  here when *you* propose a subsystem.

## How we work

- **Branch → PR → review → merge.** Never commit directly to `main` (except your
  own journal — see below). Branch off `main`, push, open a pull request, get a
  review, then merge.
- **Keep the suite green.** Run `uv run pytest -q` before you open a PR; a PR
  should leave `main` green. New behavior comes with new tests. We keep code
  `black`-clean (`uv run black .`).
- **Small, focused PRs** land faster than big ones. One idea per PR.
- **Stacked PRs: merge the base first.** If PR B builds on PR A's branch, A must
  merge (and B retarget to `main`) before B can land — nothing merges in
  isolation. And don't delete a branch that still has open PRs stacked on it
  (it auto-closes them). When in doubt, ask in Slack.
- **Ask early.** A blocker written down in your journal or dropped in Slack is
  how you get unstuck fastest — that's the point of both.

## The daily research journal (please do this)

We keep a lightweight **daily lab notebook** so the whole team — and Chris — can
see what everyone's working on without interrupting you. Think honest notes, not
polished writeups: a few lines a day.

- **One file per person:** `journal/<firstname>.md`. Yours is
  [`journal/dren.md`](../journal/dren.md) — already started for you.
- **A dated entry each day you work,** newest on top, using the template in
  [`journal/README.md`](../journal/README.md):
  ```markdown
  ## YYYY-MM-DD
  **Focus:** <the issue/topic you're on>
  **Done today:**
  - ...
  **Blockers / questions:**
  - ... (write "none" if none)
  **Next:**
  - ...
  ```
- Link issues/PRs with `#` (e.g. `#42`) so they auto-link on GitHub.
- **It's fine to push journal updates straight to `main`** — no PR needed.
- Don't delete old entries; the history is the point. Read
  [`journal/README.md`](../journal/README.md) for the full convention (and note
  the design-notes-vs-journal distinction: big proposals go in `docs/design/`).

## Getting help

- **Slack** for questions, pairing, and "is this the right approach?" — ask early
  and often.
- **Your journal's "Blockers"** line is the async version — write the blocker
  down and someone will often unblock you before you have to ask.
