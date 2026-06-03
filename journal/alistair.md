# Alistair's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

## 2026-06-02

**Focus:** addressing review feedback and landing yesterday's PRs; started #7 (time model)

**Done today:**
- Addressed review on #13: rebased onto `main` to resolve the duplicate `pytest` entry in `setup.py`, and moved `test_agent_layer.py` into `tests/` to standardize test location.
- Merged #13 (squash) after #11; closed #12 in favor of the journal convention now on `main`.
- Continued #7 (time model) on **draft PR #15** (still WIP, not merged). Reworked it later in the day to build on the #6 trigger system instead of being a parallel mechanism: rebased/stacked the branch on PR #16 (#6 event log + triggers), which must merge first. `schedule_event` is now **sugar for a non-repeatable `at_turn(turn)` trigger** rather than its own post-round hook, so scheduled events follow trigger semantics (fire once in the react phase, recorded in the event log) — one loop, one clock, one react phase. Recurring events re-schedule themselves or use `add_trigger` with `every(n)`.
- Current shape on the branch: stateless `GameClock` (`clock.py`, turn → in-game time + named day periods), opt-in `Game(time_config=...)`, time shown in prompt/`describe()`/`describe_for()`, clock config serialization, now 34 offline tests in `tests/test_time_model.py` (full branch suite 91 passing).
- Deliberately deferred in #15: time-of-day in location descriptions (blocked on the `View` work, #9), webapp time display, and an NPC-schedule example.

**Blockers / questions:**
- (Resolved) Had a design question on whether `schedule_event` should stay its own mechanism or become sugar for #6's timer triggers — settled on building it on the #6 trigger system (`at_turn(turn)`), so we don't ship two overlapping time mechanisms. #15 now stacked on #16; **#16 needs to merge first**, then rebase #15 onto `main` and retarget before it can land.

**Next:**
- Start issue #3 (Agent class on the agent layer), on its own branch.
- Land #15 once #16 merges (rebase onto `main`, retarget, final review).

## 2026-06-01

**Focus:** test infrastructure + #2 mock LLM client

**Done today:**
- Opened #11: fixed `Thing.get_property()` fallback in `things/base.py`, added `pytest` to deps, and added `tests/test_base.py`. (Merged.)
- Opened #13 for issue #2: deterministic `MockLlmClient` in `llm_client.py` (queued responses + callable responder, call recording, `None` = simulated API failure), plus `test_agent_layer.py` covering keyword fast-path, LLM fallbacks, failure handling, and the ReAct retry path. Added `docs/TESTING.md`.
- Opened #12 to store multi-agent design iteration notes for reference. (Later closed.)

**Blockers / questions:**
- none

**Next:**
- Get #11 and #13 reviewed/merged (rebase #13 after #11 lands).
