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

import concurrent.futures

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
    maybe_react,
    maybe_revise_plan,
    memories_for_frame,
    memory_stream_for_persona,
    observe_and_decide,
    remember_outcome,
    score_new_memories,
)
from backend.drives import accrue_thirst
from .sim_clock import SimClock
from .sim_config import CognitionConfig
from .world_map import WorldMap

WALK_EMOJI = "\U0001f6b6"  # person walking
SICK_EMOJI = "\U0001f922"  # nauseated face -- the #300 on-screen sickness cue


def _resting_pron(char, schedule, matched, name, emoji):
    """The emoji for a settled or mid-action agent, resolved through one
    authority chain (#581): the model's explicit pick wins; else the #300
    health cue (a sick agent wears the queasy face until it recovers); else the
    scheduled stop's emoji when on-plan, or the persona default. Health is a low
    priority *overlay* rather than a frame-time override, so a real brain's
    chosen emoji is never masked and future status effects extend this one place
    instead of stacking ternaries in the frame assembler."""
    model_emoji = getattr(char.agent, "last_emoji", None)
    if model_emoji:
        return model_emoji
    base = (schedule.emoji or emoji[name]) if matched else emoji[name]
    return SICK_EMOJI if char.get_property("is_sick") else base


# A backend-local revision reason (#581): the brain performed somewhere other
# than the scheduled stop. RevisionTrigger.reason is a plain string
# (planning.py), so this needs no engine change -- it rides godot-ga-main with
# the rest of the pacing work.
DEVIATED = "deviated"


def _decide_for(game, char, step_idx, retrieval, clock=None, stop_since=0):
    """Stamp the agent's LLM-usage context, then observe + decide (one call).

    The single decision entry point for both the serial path (called inline
    from :func:`step`'s main loop) and the parallel path (submitted to the
    decide executor, issue #366). The context stamp targets *this agent's own*
    client -- under a real brain the live server gives every agent its own
    instance precisely so concurrent stamps can't clobber each other.
    ``clock`` and ``stop_since`` (the step the agent's current schedule stop
    began) feed the decide-context block (#580) in the prompt.
    """
    # Attribute this LLM call to the persona and step (usage.py). The
    # "role" key is read by the terminal request monitor (llm_monitor)
    # to label the line; plain UsageLedgers ignore it.
    ctx = getattr(char.agent.llm_client, "context", None)
    if ctx is not None:
        ctx.update(
            {"actor": char.name, "turn": step_idx, "attempt": 0, "role": "decide"}
        )
    # Observe (perceive + retrieve memories) -> decide -> remember the
    # outcome, the same shape react_behavior gives engine NPCs. The usage
    # context above is set first so the decide() call inside
    # observe_and_decide is attributed to this persona/step.
    return observe_and_decide(
        game, char, step_idx, retrieval=retrieval, clock=clock, stop_since=stop_since
    )


def _result_or_none(fut):
    """A finished decide future's answer, or ``None`` if the call raised --
    the same degrade as a brain outage: the agent idles this tick and is
    re-asked at its next decision point."""
    try:
        return fut.result()
    except Exception:
        return None


def _minutes_to_steps(minutes, clock) -> int:
    """Whole steps spanning ``minutes`` of in-game time (at least 1) via the run's
    SimClock -- the single minutes->steps conversion the pacing code uses (#581)."""
    return max(1, clock.steps_for_seconds(int(minutes * 60)))


def _model_duration_steps(agent, clock, cog) -> int | None:
    """The model's chosen activity duration in *steps*, clamped, or None (#581).

    The tool arg is in minutes (the unit the #580 decide-context block shows the
    brain); converting to steps needs the run's SimClock, so with no clock (the
    offline tests/bake) a model duration is ignored and the caller uses the
    authored schedule instead. Only a model estimate is clamped -- an authored
    ``schedule.steps`` is trusted as-is."""
    minutes = getattr(agent, "last_duration_minutes", None)
    if minutes is None or clock is None:
        return None
    minutes = max(cog.duration_min_minutes, min(cog.duration_max_minutes, minutes))
    return _minutes_to_steps(minutes, clock)


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
    active_conversations: dict | None = None,
    react_state: dict | None = None,
    cog: CognitionConfig | None = None,
    decide_executor: concurrent.futures.Executor | None = None,
    decide_timeout: float | None = None,
    decide_pending: dict | None = None,
    decide_info: dict | None = None,
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
    the movement frame for this step plus how many conversations *completed* this
    step (issue #371: a meeting spans ticks, so this counts endings, not starts;
    used only for :func:`simulate`'s stdout heartbeat -- the frame is the
    byte-identical artifact the determinism tests and the Penn bake pin).

    ``conversation_cooldowns`` defaults to a throwaway dict and ``cog`` to
    ``CognitionConfig()`` so a caller can drive a bare tick without threading
    every knob; :func:`simulate` always passes the run-level ones it owns.

    Concurrent decisions (issue #366): when ``decide_executor`` is given, every
    agent at a decision point this tick decides *in parallel* against the
    turn-start snapshot (the engine's gather->resolve simultaneous round is the
    semantic precedent), and effects still resolve serially in ``order``. A
    decision that outlives ``decide_timeout`` seconds degrades to ``None``
    (idle this tick -- exactly the brain-outage behavior) and its still-running
    future is parked in the caller-owned ``decide_pending`` dict so the agent
    is never asked twice at once; once the parked call resolves, its answer is
    *applied* at the agent's next decision point rather than discarded --
    throwing a completed decision away would desync any stateful brain (the
    mock consumes an authored command per ask) and pay a real provider twice
    for one decision. Because the timeout contract and the double-ask guard
    only work when both knobs are supplied, passing ``decide_executor``
    without ``decide_timeout`` or ``decide_pending`` raises ``ValueError``
    instead of silently waiting forever / dropping the guard. ``decide_info``
    (optional out-param dict, the ``out_memories`` pattern) is filled with
    ``{"deciders": int, "timeouts": [names]}`` for pacing/observability. With
    ``decide_executor=None`` (the default, and always for :func:`simulate`'s
    deterministic bakes) the path is byte-identical serial.
    """
    if decide_executor is not None:
        # Fail loud: with a timeout of None one hung decide would block wait()
        # forever, and without the registry a timed-out agent would be
        # re-submitted every tick while its old call still runs.
        if decide_timeout is None:
            raise ValueError("decide_executor requires decide_timeout")
        if decide_pending is None:
            raise ValueError("decide_executor requires decide_pending")
    # Multi-tick conversations (#371) carry their in-progress state in
    # active_conversations across ticks. A None default would hand maybe_converse a
    # throwaway dict every tick, so a meeting could never advance: each tick would
    # restart it, re-greet, and re-pin the pair -- which would then never resume
    # their schedule. A caller that enables conversation must therefore own a
    # persistent dict (simulate() and PennStepper both do); callers that don't
    # converse leave both flags off.
    if conversation_enabled and active_conversations is None:
        raise ValueError(
            "conversation_enabled requires a persistent active_conversations dict "
            "(#371): without it a multi-tick meeting restarts every tick and the "
            "pair never advances or unpins"
        )
    conversation_cooldowns = (
        conversation_cooldowns if conversation_cooldowns is not None else {}
    )
    cog = cog if cog is not None else CognitionConfig()

    # React gate (#370): edge-triggered encounter detection needs memory of
    # who was already in range last tick. A throwaway dict would make every
    # tick look like a fresh encounter and storm the brain with react
    # consults, so -- like active_conversations above -- a caller that enables
    # react must own a persistent dict.
    if conversation_enabled and cog.react_enabled and react_state is None:
        raise ValueError(
            "react_enabled requires a persistent react_state dict (#370): "
            "with a throwaway dict every tick looks like a fresh encounter "
            "and the react consult fires every single tick"
        )

    # Give per-agent memory a coherent time axis: the step index is the "turn"
    # memories are stamped and scored against (issue #75). The custom loop never
    # calls end_turn, so without this game.turn would stay 0 and recency could
    # never tell memories apart.
    game.turn = step_idx

    # Schedule-advance pre-pass. Hoisted from the main loop (issue #366): each
    # block reads and mutates only its own agent's state, so running them for
    # everyone before anyone decides is byte-identical to the old interleaving
    # -- and it means the full set of decision-due agents is known up front,
    # which is what the concurrent fan-out below needs.
    due = []
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

        # Has the current activity run its course? (#581) Advance the stop
        # pointer ONLY if the completed activity happened at the scheduled place
        # (on-plan). A deviation keeps the pointer -- the scheduled stop never
        # ran, so advancing would silently skip it -- and just un-latches so the
        # agent re-decides. The mock is always on-plan, so this is byte-identical.
        if (
            st["performing"]
            and st["perform_until"] is not None
            and step_idx >= st["perform_until"]
            and not st.get("conversing")
        ):
            if st.get("on_plan", True):
                if char.agent.schedule.advance():
                    st["performing"] = False
                    # A new stop begins now: the decide-context block (#580)
                    # measures "how long on this stop" from here (re-anchored
                    # again on arrival if the stop needs a walk).
                    st["stop_since"] = step_idx
                st["perform_until"] = None
            else:
                # Deviation completed: keep the pointer, un-latch, re-anchor the
                # elapsed clock so the next decision starts fresh.
                st["performing"] = False
                st["perform_until"] = None
                st["stop_since"] = step_idx

        if not st["path"] and not st["performing"] and not st.get("conversing"):
            due.append(name)

    # Concurrent decisions (#366): everyone due this tick decides in parallel
    # against the turn-start snapshot; effects still resolve serially below.
    # The decide phase is read-only on `game` and writes only per-agent memory,
    # which is what makes the fan-out safe.
    decided = {}
    timeouts = []
    if decide_executor is not None and due:
        pending = decide_pending
        futs = {}
        for name in due:
            stale = pending.get(name)
            if stale is not None:
                if stale.done():
                    # The parked call from an earlier timeout has resolved:
                    # apply its answer now. No new decide is submitted.
                    del pending[name]
                    decided[name] = _result_or_none(stale)
                else:
                    # Still thinking since an earlier tick: keep idling, never
                    # double-submit -- one in-flight decision per agent.
                    decided[name] = None
                continue
            futs[name] = decide_executor.submit(
                _decide_for,
                game,
                chars[name],
                step_idx,
                retrieval,
                clock=clock,
                stop_since=state[name].get("stop_since", 0),
            )
        if futs:
            # One shared wall-clock window: the futures started together, so
            # this IS the per-decision budget. It composes with (rather than
            # replaces) the client's internal #260 retry/timeout budget --
            # whatever those would allow, the tick moves on at this deadline.
            concurrent.futures.wait(futs.values(), timeout=decide_timeout)
            for name, fut in futs.items():
                if fut.done():
                    decided[name] = _result_or_none(fut)
                else:
                    # Timed out. A sync call can't be cancelled, so park the
                    # future and idle the agent for this tick. When the hung
                    # call eventually completes its usage still lands in the
                    # shared ledger -- crash-free because CPython's list
                    # append/iterate are GIL-atomic, though the cost ceiling
                    # check at the top of the next tick may miss a cost that
                    # hasn't landed yet (the kill-switch can fire one tick
                    # late; the lag is bounded by the client's own #260
                    # timeout budget). The straggler may read `game` while the
                    # serial phase below mutates it -- torn perception is
                    # possible but contained: its observations were already
                    # recorded before the blocking call, and its answer is
                    # applied only at a decision point.
                    pending[name] = fut
                    decided[name] = None
                    timeouts.append(name)
    if decide_info is not None:
        decide_info.update(deciders=len(due), timeouts=timeouts)

    frame = {}
    for name in order:
        char = chars[name]
        st = state[name]

        # Opt-in thirst drive (#594): accrue once per character per step,
        # before that character's own decision below, so a just-crossed
        # IS_THIRSTY is visible to the same tick's decide. Unconditional (not
        # gated on `due`) because a walking/performing agent still gets
        # thirsty between decisions. A no-op for any persona without
        # thirst_rate, so the default bake is untouched.
        accrue_thirst(char)

        # Decision point: idle and not yet settled into an activity. The
        # pre-pass above already evaluated exactly that predicate into `due`
        # (nothing between the two passes touches another agent's state), so
        # membership keeps the fan-out and this resolve loop agreeing on the
        # same set by construction.
        if name in due:
            command = (
                decided[name]
                if name in decided
                else _decide_for(
                    game,
                    char,
                    step_idx,
                    retrieval,
                    clock=clock,
                    stop_since=st.get("stop_since", 0),
                )
            )
            # Capture the thinking behind this decision for the replay card: the
            # reasoning the agent produced and the memories it retrieved (stashed
            # on the agent by observe_and_decide). They persist on st until the
            # agent's next decision. Skipped while a timed-out decision is still
            # in flight -- the straggler thread owns those attributes just then,
            # and the card should keep showing the last real decision instead of
            # a half-made one.
            if decide_pending is None or name not in decide_pending:
                st["reasoning"] = (
                    getattr(char.agent, "last_reasoning", None) or "(no reasoning)"
                )
                st["memories"] = memories_for_frame(
                    getattr(char.agent, "last_retrieved", None)
                )
            if command and game.parser.parse_command(command, actor=char):
                remember_outcome(char, command, step_idx)
                # LLM-scored poignancy (issue #583): override this tick's new
                # memories' importance with the model's 1-10 scores BEFORE the
                # reflection check, so reflection timing tracks scored salience.
                # A no-op for the mock brain (gated on brain-identity), so the
                # bake stays byte-identical.
                score_new_memories(char, step_idx)
                # Periodic memory synthesis (issue #84): now that this step's
                # outcome is in memory, reflect if enough importance has accrued.
                # A no-op unless a reflector was wired on (real provider only), so
                # the mock replay stays byte-identical.
                maybe_reflect(char.agent, game)
                # #581: the model duration this decision carried (clamped, in
                # steps) or None -- computed once here, driving both the settle
                # trigger and perform_until below.
                model_duration_steps = _model_duration_steps(char.agent, clock, cog)
                if command.startswith("travel"):
                    dest = char.location
                    address = getattr(dest, "tile_address", None)
                    # Furniture is a per-stop bias; on a deviation the scheduled
                    # stop's furniture is for the wrong place, so drop it. The
                    # mock only ever travels to its scheduled stop, so it keeps
                    # the hint -> byte-identical.
                    stop_place = getattr(char.agent.schedule, "destination", None)
                    furniture = (
                        getattr(char.agent.schedule, "furniture", None)
                        if dest is not None and dest.name == stop_place
                        else None
                    )
                    st["path"] = (
                        world_map.walk_path(st["tile"], address, furniture=furniture)
                        if address
                        else []
                    )
                    st["pron"] = WALK_EMOJI
                    st["desc"] = f"walking to {dest.name} @ {address}"
                elif command.startswith("perform") or model_duration_steps is not None:
                    # Settle into an in-place activity. The trigger is "perform,
                    # OR any action that carried a model duration" -- so a future
                    # duration-bearing verb (#446 study/eat) settles here too,
                    # while the #300 instantaneous verbs (get/drink/activate),
                    # which carry no duration and aren't "perform", keep falling
                    # through as one-tick actions (byte-identical).
                    st["performing"] = True
                    schedule = char.agent.schedule
                    # Place-match is the pacing-relevant signal: standing at the
                    # scheduled stop means this completed that stop (a different
                    # activity at the right place is a believability matter for
                    # the #584 eval, not a pacing desync). A place mismatch is a
                    # deviation (handled by Task 4's advance gating + revision).
                    stop_place = getattr(schedule, "destination", None)
                    matched = (
                        char.location is not None and char.location.name == stop_place
                    )
                    st["on_plan"] = matched
                    activity = char.get_property("activity") or "spending time"
                    if not matched:
                        # Off-plan: let the planner rewrite the stale tail so the
                        # written plan (and #580's context block / read_plan)
                        # catch up with reality. Cooldown-guarded because each
                        # revise is a real LLM call under a live planner; the
                        # mock's revise is a no-op regardless, so the bake is
                        # untouched. Stamp on every attempt (not just successes)
                        # to bound planner-call frequency.
                        last_dev = st.get("last_deviation_revision")
                        cooldown = cog.deviation_cooldown_steps
                        if last_dev is None or step_idx - last_dev >= cooldown:
                            st["last_deviation_revision"] = step_idx
                            maybe_revise_plan(
                                char,
                                RevisionTrigger(DEVIATED, step_idx, activity),
                                clock,
                            )
                    # Emoji via the shared authority chain (model pick > #300
                    # health cue > stop-when-on-plan / persona default).
                    st["pron"] = _resting_pron(char, schedule, matched, name, emoji)
                    # char.location can be None (the `matched` guard above assumes
                    # so); don't crash the desc line if it is.
                    where = char.location.tile_address if char.location else "?"
                    st["desc"] = f"{activity} @ {where}"
                    # Duration: the model's clamped estimate (in steps) if it gave
                    # one, else the authored schedule.steps (trusted as-is, so the
                    # mock bake is untouched). A None schedule step means "stay put"
                    # -- correct for an on-plan end-of-day stop, but a deviation
                    # must never freeze there with no way to re-decide, so an
                    # off-plan perform with no bound gets the max-duration ceiling.
                    if model_duration_steps is not None:
                        st["perform_until"] = step_idx + model_duration_steps
                    else:
                        schedule_steps = schedule.steps
                        if schedule_steps is not None:
                            st["perform_until"] = step_idx + schedule_steps
                        elif matched or clock is None:
                            # On-plan stay-put (or offline, no clock to bound with):
                            # settle here for the rest of the run, as before.
                            st["perform_until"] = None
                        else:
                            # Off-plan with no bound anywhere: cap it so the brain
                            # re-decides instead of freezing on the deviation.
                            st["perform_until"] = step_idx + _minutes_to_steps(
                                cog.duration_max_minutes, clock
                            )
                else:
                    # An instantaneous authored command (#300 get/drink/boil):
                    # no walk, no settle, so neither branch above fired -- but
                    # the frame still needs refreshing, or it renders the stale
                    # "walking to ..." desc and walk emoji for the whole stop
                    # while the agent stands there acting. Stamp the current
                    # activity + location and route the emoji through the same
                    # authority chain, so the sicken/recover transition (which
                    # happens on exactly these drink commands) flips the health
                    # cue here rather than via a frame-time override.
                    schedule = char.agent.schedule
                    stop_place = getattr(schedule, "destination", None)
                    matched = (
                        char.location is not None and char.location.name == stop_place
                    )
                    st["pron"] = _resting_pron(char, schedule, matched, name, emoji)
                    activity = char.get_property("activity") or "spending time"
                    where = char.location.tile_address if char.location else "?"
                    st["desc"] = f"{activity} @ {where}"
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

        # Advance one tile along any active walk -- unless pinned mid-walk by
        # a react-started conversation (#370). Inert before #370: a
        # conversation could only ever start between settled agents, whose
        # path is empty, so no pinned agent ever had tiles left to walk.
        # The character mirrors the state tile so TiledGame.can_perceive
        # judges distance from where the agent actually stands, not its
        # spawn point (issue #662).
        if st["path"] and not st.get("conversing"):
            st["tile"] = st["path"].pop(0)
            chars[name].tile = tuple(st["tile"])
            if not st["path"]:
                # Arrived: re-anchor the decide-context clock (#580) so
                # "how long on this stop" counts time AT the stop --
                # commensurate with the planned minutes, which budget the
                # activity itself, not the walk there.
                st["stop_since"] = step_idx

        frame[name] = {
            "movement": [int(st["tile"][0]), int(st["tile"][1])],
            # Emoji is resolved into st["pron"] at each decision (travel / perform
            # / instantaneous command) through _resting_pron's authority chain --
            # including the #300 sickness cue -- so the frame just carries it.
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
        # React-or-continue (#370): BEFORE the conversation pass, so a greet's
        # first line is spoken this same tick by maybe_converse's advance
        # phase. Off by default (cog.react_enabled) -> byte-identical.
        if cog.react_enabled:
            maybe_react(
                chars,
                state,
                step_idx,
                conversation_cooldowns,
                order,
                react_state=react_state,
                active=active_conversations,
                cooldown_steps=cog.conversation_cooldown_steps,
                react_cooldown_steps=cog.react_cooldown_steps,
                react_hour_cap=cog.react_hour_cap,
                clock=clock,
            )
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
            line_playback_steps=cog.conversation_line_playback_steps,
            clock=clock,
            active=active_conversations,
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
    out_memory_records: dict | None = None,
    personas: list[dict] | None = None,
    build_world_fn=None,
    clock: SimClock | None = None,
    planner_client=None,
    reflector_client=None,
    llm_client=None,
    out_planner_sources: dict | None = None,
    out_plans: dict | None = None,
    out_events: list | None = None,
    out_wishes: list | None = None,
    extra_action_names: list[str] | None = None,
    stop_when=None,
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
    perception radius (``vision_r``), conversation pacing, and the cognition-tools
    flag (``cognition_tools``, issue #512 -- a real brain may consult its memory /
    beliefs / plan before deciding); ``None`` uses today's defaults. ``vision_r``
    only changes co-presence under a TiledGame, and conversation and the cognition
    tools are no-ops under the mock brain, so the mock replay is unchanged.

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

    Pass ``out_memory_records`` to collect the same streams as full engine
    records instead (each ``MemoryRecord.to_primitive()`` dict -- ids,
    embeddings, provenance included): what the #304 RunStore persists. The
    lean ``out_memories`` projection cannot rehydrate.

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

    Pass an ``out_wishes`` list to collect the run's full ``ActionWish`` log
    (issue #622) as ``to_primitive()`` dicts — the demand-signal record a
    ``propose`` (or an unparsed command, #621) leaves behind. Empty for a
    mock-brain run by construction: the mock never proposes and its authored
    commands always parse, so ``game.wishes`` stays empty for the whole day.

    Pass ``extra_action_names`` (spec §3, #300) through to :func:`attach_agents` to
    widen every agent's ``action_names`` beyond its own authored-command verbs.

    Pass ``stop_when`` (a ``game -> bool`` predicate, #676) to end the run early:
    it is checked after each step's frame is recorded, and a truthy result breaks
    the loop (the deciding step stays in the returned frames). Used by the boil
    experiment to stop the moment the outcome is decided instead of paying for
    idle live decides afterward. ``None`` (the default) runs the full ``num_steps``
    -- so the bake path is byte-identical.
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
        cognition_tools=cog.cognition_tools,
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
            # The step the agent's current schedule stop began (walking there
            # counts) -- feeds the decide-context block (#580).
            "stop_since": 0,
            # Did the last settle happen at the scheduled place? (#581) The
            # pre-pass only advances the stop pointer when this is True; a
            # deviation keeps the pointer. Defaults True so a never-performed
            # agent's first advance is safe.
            "on_plan": True,
            # Pinned while a multi-tick conversation runs (issue #371): step()'s
            # pre-pass skips schedule-advance/decision/movement for a conversing
            # agent, so the meeting isn't interrupted. Stays set through the
            # post-conversation playback hold (#673) -- the pair stands together
            # while the viewer plays the exchange back -- then clears.
            "conversing": False,
        }

    # Conversation is gated on a real brain (issue #86): the deterministic mock
    # brain never produces an utterance, so the default offline run holds no
    # conversations and the replay stays byte-identical. `cooldowns` throttles how
    # often the same pair re-converses across the run.
    conversation_enabled = llm_client is not None
    conversation_cooldowns: dict = {}
    # In-progress conversations, carried across ticks (issue #371). Bakes run the
    # SAME multi-tick form as live -- there is no separate in-tick path -- but the
    # mock never speaks, so a bake holds zero conversations and stays byte-identical.
    active_conversations: dict = {}
    # Who was already within mutual sight last tick (issue #370) -- the react
    # pass's edge detector. Persistent for the run, like the two dicts above;
    # inert unless cognition.react_enabled is set in the caller's config.
    react_state: dict = {}

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
            active_conversations=active_conversations,
            react_state=react_state,
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

        # Early termination (#676): a caller can end the run as soon as the
        # thing it measures has happened -- e.g. the boil experiment stops the
        # moment the agent drinks, rather than paying for ~75 more live decides
        # by an agent with nothing left to pursue. Checked after the frame is
        # recorded, so the deciding step stays in the replay. Never set on the
        # bake path, so the bundled replay is byte-identical.
        if stop_when is not None and stop_when(game):
            break

    # Hand back each agent's complete memory stream, if the caller asked for it.
    if out_memories is not None:
        for name in order:
            out_memories[name] = memory_stream_for_persona(chars[name].agent)

    # Same streams as full engine records (#304): to_primitive() dicts the
    # RunStore can persist and rehydrate (the lean projection above cannot).
    if out_memory_records is not None:
        for name in order:
            memory = getattr(chars[name].agent, "memory", None)
            out_memory_records[name] = (
                [r.to_primitive() for r in memory.records] if memory is not None else []
            )

    # Hand back the run's full GameEvent log, if the caller asked for it
    # (issue #467). Already-serialized EventState dicts, so bake artifacts
    # and the live feed carry the identical record.
    if out_events is not None:
        out_events.extend(event.to_primitive() for event in game.events)

    # Hand back the run's full ActionWish log, if the caller asked for it
    # (issue #622). Already-serialized WishState dicts, so bake artifacts and
    # the live feed carry the identical record. Empty under the mock brain by
    # construction (see the docstring above).
    if out_wishes is not None:
        out_wishes.extend(wish.to_primitive() for wish in game.wishes)

    return frames
