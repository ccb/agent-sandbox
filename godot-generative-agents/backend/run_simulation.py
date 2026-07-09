"""The generative-agents step loop: ``step`` (one tick) and ``simulate`` (a run).

This is the outer loop of the port. The frontend's clock (one 10-second step,
sprites walking one tile at a time) is finer-grained than the engine's
action-level turns, so the *step* loop lives here and consults the engine's
decision seam (``Agent.decide`` -> mock/LLM client) only at decision points:

* When a character is idle (no walk in progress, not yet settled into an
  activity), ask its agent what to do. ``travel`` routes through the engine
  (moving its logical location) and we ask the pathfinder for a tile route;
  ``perform`` settles it into an activity in place.
* Every step, advance one tile along any active path, then record the
  character's tile + emoji + action label into that step's movement frame.

The world is injected, not hard-coded: callers pass their own ``personas`` and a
``build_world_fn`` (a ``world_map -> (game, characters)`` builder). The project's
primary world is the UPenn campus -- :func:`penn.penn_world.build_penn_world`
configures it, the replay bake (``penn.generate_penn_replay``) drives ``simulate``
to a file, and the live server (``penn.serve_penn``) drives ``step`` tick-by-tick.
"""

import os

from text_adventure_games.embedding_client import (
    EmbeddingConfig,
    create_embedding_client,
    embedding_client_from_env,
)
from text_adventure_games.planning import (
    ACTION_FAILED,
    BEHIND_SCHEDULE,
    RevisionTrigger,
)
from text_adventure_games.npc import maybe_reflect
from text_adventure_games.reporting import Channel, Message, default_renderer
from text_adventure_games.usage import UsageLedger

from .cognition import (
    attach_agents,
    maybe_converse,
    maybe_revise_plan,
    memories_for_frame,
    memory_stream_for_persona,
    observe_and_decide,
    remember_outcome,
)
from .sim_clock import SimClock
from .sim_config import CognitionConfig
from .world_map import WorldMap

WALK_EMOJI = "\U0001f6b6"  # person walking


def resolve_embedding_client(provider: str | None):
    """Resolve a semantic-memory embedding client for the sim (issue #102).

    Precedence: an explicit ``--embeddings`` *provider* wins; otherwise fall back
    to the ``EMBEDDING_PROVIDER`` environment variable (via the engine's
    ``embedding_client_from_env``). Returns ``None`` -- keyword-overlap relevance,
    the offline default -- when neither is set, or when the chosen backend can't
    be created (e.g. the ``embeddings`` extra isn't installed). That graceful
    degrade is what keeps the plain ``run_simulation`` run free, offline, and
    CI-safe even with a default-on flag.

    Either way the deterministic mock brain decides from location alone, so the
    exported replay stays byte-identical; an embedding client only reorders the
    (mock-ignored) retrieved-memory block.
    """
    if not provider:
        return embedding_client_from_env()
    try:
        config = EmbeddingConfig(
            provider=provider,
            model=os.environ.get("EMBEDDING_MODEL"),
            api_key=os.environ.get("EMBEDDING_API_KEY"),
            base_url=os.environ.get("EMBEDDING_BASE_URL"),
        )
        return create_embedding_client(config)
    except (ImportError, ValueError) as e:
        print(
            f"Warning: could not create embedding client ({e}); falling back "
            "to keyword-overlap relevance."
        )
        return None


def step(
    game,
    chars: dict,
    state: dict,
    step_idx: int,
    *,
    order: list,
    world_map: WorldMap,
    emoji: dict,
    retrieval=None,
    clock: SimClock | None = None,
    conversation_enabled: bool = False,
    conversation_cooldowns: dict | None = None,
    cog: CognitionConfig | None = None,
) -> tuple[dict, int]:
    """Run exactly one 10-second tick and return ``(frame, chats_this_step)``.

    This is the one-tick seam extracted from :func:`simulate` (issue #296):
    schedule advance -> decision point (observe -> decide -> precondition gate ->
    remember/reflect) -> one tile of walking -> frame assembly, then
    ``maybe_converse`` for co-located residents. ``simulate`` is now a thin loop
    over this function, and a live backend (#349) drives it tick-by-tick so it can
    ship each frame the moment it exists.

    Self-contained by design: no file I/O, no globals, no sleeping. It mutates
    ``state``, ``conversation_cooldowns`` and ``game.turn`` in place and returns
    the movement frame for this step plus how many conversations fired (the
    latter only for :func:`simulate`'s stdout heartbeat; the frame is the
    byte-identical artifact the determinism tests and the Penn bake pin).

    ``conversation_cooldowns`` defaults to a throwaway dict and ``cog`` to
    ``CognitionConfig()`` so a caller can drive a bare tick without threading
    every knob; :func:`simulate` always passes the run-level ones it owns.
    """
    conversation_cooldowns = (
        conversation_cooldowns if conversation_cooldowns is not None else {}
    )
    cog = cog if cog is not None else CognitionConfig()

    # Give per-agent memory a coherent time axis: the step index is the "turn"
    # memories are stamped and scored against (issue #75). The custom loop never
    # calls end_turn, so without this game.turn would stay 0 and recency could
    # never tell memories apart.
    game.turn = step_idx
    frame = {}
    for name in order:
        char = chars[name]
        st = state[name]

        # Behind-schedule trigger (design doc §8): a new in-game hour began and
        # this agent is still walking, not yet at its planned stop. Offer its
        # planner a chance to re-plan the tail. Clock-gated, so tests that pass no
        # clock skip it; the mock's revise is a no-op regardless.
        if (
            clock is not None
            and step_idx > 0
            and st["path"]
            and clock.hour_at(step_idx) != clock.hour_at(step_idx - 1)
        ):
            maybe_revise_plan(char, RevisionTrigger(BEHIND_SCHEDULE, step_idx), clock)

        # Has the current activity run its course? Un-latch and point the brain
        # at the next scheduled stop, so the agent becomes idle below and walks
        # on. When the schedule is exhausted, just stop the timer and let it
        # settle into this last activity for the rest of the run.
        if (
            st["performing"]
            and st["perform_until"] is not None
            and step_idx >= st["perform_until"]
        ):
            if char.agent.schedule.advance():
                st["performing"] = False
            st["perform_until"] = None

        # Decision point: idle and not yet settled into an activity.
        if not st["path"] and not st["performing"]:
            # Attribute this LLM call to the persona and step (usage.py). The
            # "role" key is read by the terminal request monitor (llm_monitor)
            # to label the line; plain UsageLedgers ignore it.
            ctx = getattr(char.agent.llm_client, "context", None)
            if ctx is not None:
                ctx.update(
                    {"actor": name, "turn": step_idx, "attempt": 0, "role": "decide"}
                )
            # Observe (perceive + retrieve memories) -> decide -> remember the
            # outcome, the same shape react_behavior gives engine NPCs. The usage
            # context above is set first so the decide() call inside
            # observe_and_decide is attributed to this persona/step.
            command = observe_and_decide(game, char, step_idx, retrieval=retrieval)
            # Capture the thinking behind this decision for the replay card: the
            # reasoning the agent produced and the memories it retrieved (stashed
            # on the agent by observe_and_decide). They persist on st until the
            # agent's next decision.
            st["reasoning"] = (
                getattr(char.agent, "last_reasoning", None) or "(no reasoning)"
            )
            st["memories"] = memories_for_frame(
                getattr(char.agent, "last_retrieved", None)
            )
            if command and game.parser.parse_command(command, actor=char):
                remember_outcome(char, command, step_idx)
                # Periodic memory synthesis (issue #84): now that this step's
                # outcome is in memory, reflect if enough importance has accrued.
                # A no-op unless a reflector was wired on (real provider only), so
                # the mock replay stays byte-identical.
                maybe_reflect(char.agent, game)
                if command.startswith("travel"):
                    dest = char.location
                    address = getattr(dest, "tile_address", None)
                    st["path"] = (
                        world_map.walk_path(st["tile"], address) if address else []
                    )
                    st["pron"] = WALK_EMOJI
                    st["desc"] = f"walking to {dest.name} @ {address}"
                elif command.startswith("perform"):
                    st["performing"] = True
                    # Per-stop emoji (the schedule may vary it from the persona's
                    # default), falling back to the persona's.
                    st["pron"] = char.agent.schedule.emoji or emoji[name]
                    activity = char.get_property("activity") or "spending time"
                    st["desc"] = f"{activity} @ {char.location.tile_address}"
                    # Schedule the move on to the next stop. None steps means
                    # "stay" -- the agent settles here for the rest of the run.
                    duration = char.agent.schedule.steps
                    st["perform_until"] = (
                        step_idx + duration if duration is not None else None
                    )
            elif command:
                # The agent chose a command but it failed the precondition gate.
                # Offer its planner a chance to re-plan around the blocked action
                # (design doc §8). The mock never lands here -- its travel/perform
                # are always legal -- so this stays byte-identical; it's the seam a
                # real planner needs.
                reason = getattr(game.parser, "last_fail_message", "") or command
                maybe_revise_plan(
                    char, RevisionTrigger(ACTION_FAILED, step_idx, reason), clock
                )

        # Advance one tile along any active walk.
        if st["path"]:
            st["tile"] = st["path"].pop(0)

        frame[name] = {
            "movement": [int(st["tile"][0]), int(st["tile"][1])],
            "pronunciatio": st["pron"],
            "description": st["desc"],
            # The agent's latest dialogue line (issue #86), or None. Updated below
            # by maybe_converse for any pair that talks this step.
            "chat": st["chat"],
            # Reasoning + retrieved memories for this agent's card (the exporter
            # writes the frame verbatim, so these flow straight into
            # movement/<step>.json for the replay to render).
            "reasoning": st["reasoning"],
            "memories": st["memories"],
        }

    # Conversation (issue #86): after everyone has moved, let co-located, settled
    # residents talk. Each meeting writes dialogue into both agents' memory
    # streams and updates their cards' chat line. Gated + a no-op for the mock
    # brain, so the default replay is unchanged.
    chats_this_step = 0
    if conversation_enabled:
        chats_this_step = maybe_converse(
            game,
            chars,
            state,
            frame,
            step_idx,
            conversation_cooldowns,
            order,
            cooldown_steps=cog.conversation_cooldown_steps,
            max_exchanges=cog.conversation_max_exchanges,
        )
    return frame, chats_this_step


def simulate(
    world_map: WorldMap,
    num_steps: int,
    ledger: UsageLedger | None = None,
    embedding_client=None,
    *,
    retrieval=None,
    cognition=None,
    relationships_csv: str | None = None,
    base_personas_dir: str | None = None,
    out_memories: dict | None = None,
    personas: list[dict] | None = None,
    build_world_fn=None,
    clock: SimClock | None = None,
    planner_client=None,
    reflector_client=None,
    llm_client=None,
    out_planner_sources: dict | None = None,
    out_plans: dict | None = None,
    out_events: list | None = None,
    extra_action_names: list[str] | None = None,
) -> list[dict]:
    """Run the simulation and return one movement frame per step.

    Each frame is ``{persona_name: {movement, pronunciatio, description, chat}}``.
    Builds its own game + agents, so it is self-contained and easy to test.

    Pass a shared ``ledger`` to accumulate per-agent LLM token/cost accounting
    across the run (usage.py); the mock brain records zero cost, so the numbers
    are $0 until a real client is wired in (NEXT-STEPS Phase A).

    Pass an optional ``embedding_client`` (issue #76) for semantic memory
    relevance. The mock brain decides from location alone, so the frames are
    byte-identical with or without it; only the retrieved-memory block changes.

    Pass an optional ``retrieval`` (:class:`sim_config.RetrievalConfig`) to tune
    the memory-retrieval scoring; ``None`` uses the engine defaults. As above, the
    mock brain ignores the retrieved block, so the frames stay byte-identical --
    only *which* memories surface changes.

    Pass an optional ``cognition`` (:class:`sim_config.CognitionConfig`) to set the
    perception radius (``vision_r``) and conversation pacing; ``None`` uses today's
    defaults. ``vision_r`` only changes co-presence under a TiledGame, and
    conversation is a no-op under the mock brain, so the mock replay is unchanged.

    Pass ``relationships_csv`` / ``base_personas_dir`` (the upstream bootstrap
    assets) to seed each persona at t=0 -- relationships into memory, partial
    known-places into knowledge (issue #79, via :func:`attach_agents`). Both are
    optional: tests call ``simulate`` without them and stay byte-identical, while
    a real run (:func:`main`) points them at ``frontend/``.

    Pass an ``out_memories`` dict to also collect each agent's *full* memory
    stream (``{persona_name: [memory dicts]}``) at the end of the run -- the
    exporter writes it per persona so the State Details panel can show every
    memory an agent formed, not just the few retrieved per step. It's an
    out-parameter (not part of the return) so the many ``frames = simulate(...)``
    callers and the determinism tests stay unchanged.

    Pass a :class:`~backend.sim_clock.SimClock` to enable clock-based plan
    revision (issue #83): at an hour boundary an agent still en route is "behind
    schedule," a trigger its planner may react to. With no clock (the test
    default) those triggers never fire. Either way the mock planner's ``revise``
    is a no-op, so the exported frames are byte-identical -- the clock only gates
    *whether the seam is offered*, not the deterministic decisions themselves.

    Pass a ``planner_client`` (an engine ``LlmClient``) to plan each day with a
    real model (:class:`~backend.planner.LLMPlanner`); with none -- the offline
    default -- each agent replays its authored schedule via ``MockPlanner`` and the
    replay is byte-identical. The Penn runners pass one only for a non-mock provider.

    Pass an ``llm_client`` (NEXT-STEPS Phase A) to make the per-step travel/perform
    *decisions* through a real model: it becomes each agent's brain, while a
    deterministic ``ScheduleMockClient`` still paces the schedule
    (``advance``/``steps``/``emoji``). With none -- the offline default -- that mock
    client is also the brain, so decisions stay deterministic and byte-identical.
    A real ``llm_client`` also enables **conversation** (NEXT-STEPS Phase E, issue
    #86): co-located, settled residents run a turn-taking dialogue each step (via
    :func:`~backend.cognition.maybe_converse`), writing each line into both
    agents' memory streams and onto their replay cards' ``chat`` field. With the
    mock brain no utterance is produced, so no conversation happens and the replay
    stays byte-identical.

    Pass a ``reflector_client`` (an engine ``LlmClient``) to give each agent an
    ``LLMReflector`` for periodic memory synthesis (issue #84): the loop runs a
    reflection pass once an agent's accumulated importance crosses its threshold.
    With none -- the offline default -- no reflector is wired on, so reflection
    never fires and the replay is byte-identical. The Penn runners pass one only
    for a non-mock provider.

    Pass an ``out_planner_sources`` dict to collect, per persona, where its plan came
    from (``"llm"`` / ``"static"`` fallback / ``"mock"``) -- an out-parameter so the
    determinism tests' ``simulate(...)`` calls stay unchanged, so the caller can
    report how many agents the model actually planned vs. fell back.

    Pass an ``out_plans`` dict to collect each persona's generated plan
    (``{name: DailyPlan.to_primitive()}``) so the run can persist it; the exporter
    writes ``personas/<Name>/daily_plan.json`` so a downstream reader has it
    without re-calling the model. Also an out-parameter, for the same reason.

    Pass an ``out_events`` list to collect the run's full ``GameEvent`` log
    (issue #467) as ``to_primitive()`` dicts — the #305 ``EventState`` shape
    the bake artifacts persist and the live feed publishes.

    Pass ``extra_action_names`` (spec §3, #300) through to :func:`attach_agents` to
    widen every agent's ``action_names`` beyond its own authored-command verbs.
    """
    # The world is injected: a caller passes its own personas + builder (e.g.
    # penn_world's perception-gated builder). The builder receives the world_map
    # so perception (issue #82) stays tile-distance based.
    if personas is None or build_world_fn is None:
        raise ValueError(
            "simulate() requires personas + build_world_fn -- build them from a "
            "world YAML (see penn.penn_world.build_penn_world)."
        )
    # Cognition defaults (perception radius, conversation pacing) come from the
    # config; None means "today's behavior", i.e. CognitionConfig()'s defaults.
    cog = cognition if cognition is not None else CognitionConfig()

    game, chars = build_world_fn(world_map)
    attach_agents(
        chars,
        personas,
        ledger=ledger,
        embedding_client=embedding_client,
        relationships_csv=relationships_csv,
        base_personas_dir=base_personas_dir,
        vision_r=cog.vision_r,
        planner_client=planner_client,
        reflector_client=reflector_client,
        llm_client=llm_client,
        clock=clock,
        num_steps=num_steps,
        out_planner_sources=out_planner_sources,
        out_plans=out_plans,
        extra_action_names=extra_action_names,
    )
    emoji = {p["name"]: p["emoji"] for p in personas}
    order = [p["name"] for p in personas]

    state = {}
    for spec in personas:
        char = chars[spec["name"]]
        state[char.name] = {
            "tile": tuple(spec["start_tile"]),
            "path": [],
            "pron": emoji[char.name],
            "desc": f"waking up @ {char.location.tile_address}",
            "performing": False,
            # The step at which the current activity is done and the agent should
            # move on to its next scheduled stop (None = stay put indefinitely).
            "perform_until": None,
            # Latest reasoning + retrieved-memory block, surfaced on the replay's
            # agent card. They update at each decision point and carry forward on
            # the steps in between (like desc/pron), so the card is never blank.
            "reasoning": "(waking up)",
            "memories": [],
            # Latest dialogue line, surfaced on the replay's agent card (issue
            # #86). None until this agent has a conversation; then it persists
            # (like reasoning/desc) until the next one.
            "chat": None,
        }

    # Conversation is gated on a real brain (issue #86): the deterministic mock
    # brain never produces an utterance, so the default offline run holds no
    # conversations and the replay stays byte-identical. `cooldowns` throttles how
    # often the same pair re-converses across the run.
    conversation_enabled = llm_client is not None
    conversation_cooldowns: dict = {}

    # Heartbeat plumbing (real-brain runs only). A live run makes many blocking
    # API calls per turn with no other output during quiet stretches, which reads
    # as a hang; we emit a one-line pulse per step so progress stays visible.
    heartbeat = default_renderer()
    prev_calls = 0

    frames: list[dict] = []
    for _step in range(num_steps):
        # Cost kill-switch (issue #183): stop before starting a step we may not be
        # able to afford. Checked once per step, so the actual spend can overshoot
        # the ceiling by up to one step's worth of calls -- a guard against a
        # runaway live run, not a precise cap. A no-op unless the ledger carries a
        # ceiling (max_cost_usd); the free mock brain spends $0 and never trips it.
        if ledger is not None and ledger.over_budget():
            heartbeat.emit(
                Message(
                    Channel.SYSTEM,
                    f"LLM cost ceiling ${ledger.max_cost_usd:.4f} reached "
                    f"(${ledger.total_cost_usd():.4f} over {len(ledger.records)} "
                    f"calls) -- stopping at step {_step}/{num_steps}. "
                    "Writing the partial replay.",
                )
            )
            break
        # One 10-second tick, extracted to step() (#296) so a live backend can
        # drive the sim between frames. simulate() stays the thin loop: it owns
        # run-level concerns (the budget gate above, the heartbeat below, the
        # final memory-stream fill) and hands each tick to step(). The frame is
        # byte-identical to the inline loop; chats_this_step feeds the heartbeat.
        frame, chats_this_step = step(
            game,
            chars,
            state,
            _step,
            order=order,
            world_map=world_map,
            emoji=emoji,
            retrieval=retrieval,
            clock=clock,
            conversation_enabled=conversation_enabled,
            conversation_cooldowns=conversation_cooldowns,
            cog=cog,
        )
        frames.append(frame)

        # Per-turn heartbeat: stdout only, so it never touches the exported
        # frames -- the mock replay stays byte-identical. Gated on a real client
        # because that is the only run slow enough to look stalled.
        if llm_client is not None:
            total_calls = ledger.summary()["calls"] if ledger else 0
            delta = total_calls - prev_calls
            prev_calls = total_calls
            when = (
                clock.time_at(_step).strftime("%H:%M:%S")
                if clock is not None
                else f"step {_step}"
            )
            chat_note = f" · {chats_this_step} chat(s)" if chats_this_step else ""
            heartbeat.emit(
                Message(
                    Channel.SYSTEM,
                    f"Turn {_step + 1}/{num_steps} · {when} · "
                    f"+{delta} LLM calls ({total_calls} total){chat_note}",
                )
            )

    # Hand back each agent's complete memory stream, if the caller asked for it.
    if out_memories is not None:
        for name in order:
            out_memories[name] = memory_stream_for_persona(chars[name].agent)

    # Hand back the run's full GameEvent log, if the caller asked for it
    # (issue #467). Already-serialized EventState dicts, so bake artifacts
    # and the live feed carry the identical record.
    if out_events is not None:
        out_events.extend(event.to_primitive() for event in game.events)

    return frames
