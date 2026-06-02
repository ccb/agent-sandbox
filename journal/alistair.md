# Alistair's research journal

Daily log, newest entry on top. Format: [`journal/README.md`](README.md).

<!-- Copy the template from README.md to the top each working day. -->

## 2026-06-02

**Focus:** addressing review feedback and landing yesterday's PRs; started #7 (time model)

**Done today:**
- Addressed review on #13: rebased onto `main` to resolve the duplicate `pytest` entry in `setup.py`, and moved `test_agent_layer.py` into `tests/` to standardize test location.
- Merged #13 (squash) after #11; closed #12 in favor of the journal convention now on `main`.
- Started #7 (time model) — it only depends on the existing `Game.turn` counter, so it can proceed in parallel with the agent-layer issues. Opened **draft PR #15** (WIP, not ready to merge): new stateless `GameClock` (`clock.py`, turn → in-game time + named day periods), opt-in `Game(time_config=...)`, `schedule_event(turn, callback)` fired post-round in `end_turn()`, time shown in prompt/`describe()`/`describe_for()`, clock config serialization, and 31 offline tests (`tests/test_time_model.py`; full suite 67 passing).
- Deliberately deferred in #15: time-of-day in location descriptions (blocked on the `View` work, #9), webapp time display, and an NPC-schedule example.

**Blockers / questions:**
- Design question on #15 for whoever picks up #6: scheduled events fire in the same post-round phase the trigger system will use — should `schedule_event` stay its own mechanism or become sugar for #6's timer triggers (`turn >= N`)? Want agreement before merging so we don't ship two overlapping time mechanisms.

**Next:**
- Start issue #3 (Agent class on the agent layer), on its own branch.
- Iterate on #15 based on review feedback / the #6 seam decision.

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
