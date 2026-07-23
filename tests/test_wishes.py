"""Tests for the action-wish demand channel (#620): the ActionWish record,
the Game.log_wish sink, the AGENT_WISH trace channel, and the propose verb."""

from text_adventure_games import games, things
from text_adventure_games.reporting import CaptureRenderer, Channel
from text_adventure_games.wishes import (
    ActionWish,
    TRIGGER_CRAFT_GAP,
    TRIGGER_PARSE_GAP,
    TRIGGER_PROPOSED,
)

# ----------------------------------------------------------------------
# Section A: the ActionWish record
# ----------------------------------------------------------------------


def test_action_wish_to_primitive_round_trips_all_fields():
    wish = ActionWish(
        actor="Sofia",
        turn=13,
        location="Houston Kitchen",
        desired="fill the pot from the sink",
        reason="boiling needs water in the pot",
        trigger=TRIGGER_PROPOSED,
        goals=["make the water safe to drink"],
        scope=["pot", "stove", "sink", "Diego"],
        raw_command="propose fill the pot from the sink because boiling needs water in the pot",
    )
    assert wish.to_primitive() == {
        "actor": "Sofia",
        "turn": 13,
        "location": "Houston Kitchen",
        "desired": "fill the pot from the sink",
        "reason": "boiling needs water in the pot",
        "trigger": "proposed",
        "goals": ["make the water safe to drink"],
        "scope": ["pot", "stove", "sink", "Diego"],
        "raw_command": "propose fill the pot from the sink because boiling needs water in the pot",
        "meta": {},
    }


def test_action_wish_defaults_are_empty_not_shared():
    a = ActionWish(actor=None, turn=0, location=None, desired="x")
    b = ActionWish(actor=None, turn=0, location=None, desired="y")
    a.goals.append("mutated")
    a.meta["k"] = "v"
    assert b.goals == [] and b.scope == [] and b.meta == {}
    assert a.reason == "" and a.trigger == TRIGGER_PROPOSED


def test_trigger_constants():
    # #621 (parse-gap capture) and #628 (craft-gap capture) use these reserved
    # constants; pin all three values because wishes.jsonl consumers key on
    # them (#622/#623).
    assert TRIGGER_PROPOSED == "proposed"
    assert TRIGGER_PARSE_GAP == "parse_gap"
    assert TRIGGER_CRAFT_GAP == "craft_gap"


# ----------------------------------------------------------------------
# Section B: the AGENT_WISH trace channel
# ----------------------------------------------------------------------


def tiny_game():
    """A small, isolated 2-room world (Field --north--> Forest) with a player
    and a troll, mirroring tests/test_agent_layer.py so this module stands
    alone."""
    field = things.Location("Field", "An open grassy field.")
    forest = things.Location("Forest", "A dark tangled forest.")
    field.add_connection("north", forest)
    player = things.Character("player", "a brave adventurer", "I explore.")
    troll = things.Character("troll", "a mean green troll", "I am hungry.")
    game = games.Game(field, player, characters=[troll])
    field.add_character(troll)
    return game


def test_parser_agent_wish_emits_on_wish_channel_with_meta():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.parser.agent_wish(
        "troll", "a ladder — because the wall is too high", wish={"desired": "a ladder"}
    )
    msgs = cap.by_channel(Channel.AGENT_WISH)
    assert len(msgs) == 1
    assert msgs[0].actor == "troll"
    assert msgs[0].meta == {"wish": {"desired": "a ladder"}}


def test_agent_wish_channel_is_agent_trace_and_normally_visible():
    from text_adventure_games.reporting import AGENT_CHANNELS, NORMAL, channel_visible

    # Grouped/attributed like the other ReAct trace channels, and visible at
    # NORMAL (a wish is at least as newsworthy as a reasoning line).
    assert Channel.AGENT_WISH in AGENT_CHANNELS
    assert channel_visible(Channel.AGENT_WISH, NORMAL)


def test_plain_renderer_formats_wish_line():
    from text_adventure_games.reporting import Message, PlainRenderer

    line = PlainRenderer()._format(
        Message(Channel.AGENT_WISH, "a ladder", actor="troll")
    )
    assert line == "troll [wish] a ladder"


def test_web_renderer_maps_wish_to_npc_wish_type():
    from text_adventure_games.webapp.web_parser import WebRenderer
    from text_adventure_games.reporting import Message

    web = WebRenderer()
    web.emit(Message(Channel.AGENT_WISH, "a ladder", actor="troll"))
    assert web.drain() == [{"type": "npc_wish", "text": "troll [wish] a ladder"}]


# ----------------------------------------------------------------------
# Section C: the Game sink
# ----------------------------------------------------------------------


def _wish(**overrides):
    base = dict(
        actor="troll",
        turn=1,
        location="Field",
        desired="a ladder",
        reason="the wall is too high",
    )
    base.update(overrides)
    return ActionWish(**base)


def test_log_wish_appends_and_fires_streaming_callback():
    game = tiny_game()
    assert game.wishes == []  # empty by default; games that never wish are unchanged
    seen = []
    game.on_wish = seen.append  # the UsageLedger._on_record pattern (#622's tap)
    wish = _wish()
    game.log_wish(wish)
    assert game.wishes == [wish]
    assert seen == [wish]


def test_log_wish_without_callback_is_fine_and_emits_trace():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.log_wish(_wish())
    assert len(game.wishes) == 1
    [msg] = cap.by_channel(Channel.AGENT_WISH)
    assert msg.actor == "troll"
    assert msg.text == "a ladder — because the wall is too high"
    assert msg.meta["wish"]["trigger"] == "proposed"


def test_log_wish_trace_omits_empty_reason():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.log_wish(_wish(reason=""))
    [msg] = cap.by_channel(Channel.AGENT_WISH)
    assert msg.text == "a ladder"


# ----------------------------------------------------------------------
# Section D: the propose verb
# ----------------------------------------------------------------------


def test_propose_records_a_fully_populated_wish():
    game = tiny_game()
    troll = game.characters["troll"]
    troll.add_goal("cross the wall", things.characters.GoalType.SHORT)
    ok = game.parser.parse_command(
        "propose build a ladder because the wall is too high", actor=troll
    )
    assert ok is True
    [wish] = game.wishes
    assert wish.actor == "troll"
    assert wish.trigger == TRIGGER_PROPOSED
    assert wish.desired == "build a ladder"
    assert wish.reason == "the wall is too high"
    assert wish.location == "Field"
    assert wish.turn == game.turn
    assert "cross the wall" in wish.goals
    assert "player" in wish.scope  # co-located characters are in the snapshot
    assert wish.raw_command == "propose build a ladder because the wall is too high"


def test_propose_without_because_records_empty_reason():
    game = tiny_game()
    troll = game.characters["troll"]
    assert game.parser.parse_command("propose build a ladder", actor=troll)
    [wish] = game.wishes
    assert wish.desired == "build a ladder"
    assert wish.reason == ""


def test_bare_propose_fails_and_teaches_the_format():
    game = tiny_game()
    troll = game.characters["troll"]
    assert not game.parser.parse_command("propose", actor=troll)
    assert game.wishes == []
    assert (
        "propose <the action you need> because <why>" in game.parser.last_fail_message
    )


def test_propose_payload_with_direction_words_is_not_hijacked_to_go():
    # Regression guard for the determine_intent ordering: the direction check
    # (parsing.py, "elif self.get_direction(command, ...)") runs BEFORE the
    # command-initial-verb match, so without the early propose branch this
    # command would route to GO and move the troll north.
    game = tiny_game()
    troll = game.characters["troll"]
    assert game.parser.parse_command(
        "propose climb up and go north over the wall because i am stuck", actor=troll
    )
    assert troll.location.name == "Field"  # did NOT move
    [wish] = game.wishes
    assert wish.desired == "climb up and go north over the wall"


def test_propose_payload_naming_a_multiword_alias_is_not_hijacked():
    # Regression guard for the determine_intent ordering (PR #667 review): the
    # specific-first match (`_match_specific_action`) does a naive substring
    # test, so a payload naming a multi-word alias like "talk to" used to route
    # to that action and silently drop the wish. propose must win first.
    game = tiny_game()
    troll = game.characters["troll"]
    assert game.parser.parse_command(
        "propose talk to the mayor about funding because the game has no petition verb",
        actor=troll,
    )
    [wish] = game.wishes  # the wish was recorded, TALK did not fire
    assert wish.desired == "talk to the mayor about funding"
    assert wish.reason == "the game has no petition verb"


def test_propose_succeeds_for_the_player_too():
    game = tiny_game()
    assert game.parser.parse_command("propose whistle for a dog because i am lonely")
    [wish] = game.wishes
    assert wish.actor == "player"


def test_player_propose_is_attributed_to_the_player_not_a_named_npc():
    # Regression guard (PR #667 review pass): the payload is a free-text action
    # description, so a co-located name in it ("propose talk to troll ...") must
    # NOT be mined as the proposer -- the wish and its whole context snapshot
    # belong to whoever acted (the player here), not the character they named.
    game = tiny_game()
    assert game.parser.parse_command("propose talk to troll because i have no way to")
    [wish] = game.wishes
    assert wish.actor == "player"  # not "troll"
    assert wish.location == "Field"  # the player's location, not mined context


def test_propose_lands_in_the_game_event_log():
    # parse_command logs every gate-passing action as a GameEvent — a wish is
    # an ordinary action, so recorded runs see it with zero extra plumbing.
    game = tiny_game()
    troll = game.characters["troll"]
    game.parser.parse_command("propose build a ladder because reasons", actor=troll)
    event = game.events[-1]
    assert event.action == "propose"
    assert event.actor == "troll"


def test_propose_spends_the_turn_like_any_action():
    # No FREE_ACTION flag: articulating the gap costs the turn — the wish is
    # itself measurable behavior (spec decision 2).
    from text_adventure_games.actions.wish import Propose

    assert not getattr(Propose, "FREE_ACTION", False)
    assert Propose.DURATION is None


def test_propose_appears_in_help():
    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    game.parser.parse_command("help")
    listing = "\n".join(cap.texts(Channel.NARRATION))
    assert "propose" in listing
    assert "NONE of your other actions can do what you need" in listing


# ----------------------------------------------------------------------
# Section E: the tool-calling path (#356 machinery, no changes needed)
# ----------------------------------------------------------------------


def test_tools_for_offers_propose_with_desired_and_reason_slots():
    from text_adventure_games.npc import tools_for

    game = tiny_game()
    troll = game.characters["troll"]
    tools = {t["name"]: t for t in tools_for(game.parser, actor=troll)}
    assert "propose" in tools
    props = tools["propose"]["parameters"]["properties"]
    assert set(props) == {"reasoning", "desired", "reason"}
    assert tools["propose"]["parameters"]["required"] == ["desired"]


def test_tool_call_reassembles_the_because_grammar():
    from text_adventure_games.npc import command_from_tool_call

    game = tiny_game()
    command = command_from_tool_call(
        "propose",
        {"desired": "fill the pot from the sink", "reason": "boiling needs water"},
        game.parser,
    )
    assert command == "propose fill the pot from the sink because boiling needs water"


def test_choose_action_enum_includes_propose():
    from text_adventure_games.npc import build_choose_action_tool

    game = tiny_game()
    tool = build_choose_action_tool(list(game.parser.actions))
    assert "propose" in tool["parameters"]["properties"]["action"]["enum"]


# ----------------------------------------------------------------------
# Section F: end-to-end through the ReAct loop (offline, mock brain)
# ----------------------------------------------------------------------


def test_react_agent_proposes_and_wish_flows_to_every_sink():
    from text_adventure_games.llm_client import MockLlmClient
    from text_adventure_games.npc import make_react_behavior

    game = tiny_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    troll = game.characters["troll"]
    streamed = []
    game.on_wish = streamed.append
    troll.set_behavior(
        make_react_behavior(
            MockLlmClient(
                [
                    "Reasoning: no command here lets me cross the wall\n"
                    "Action: propose build a ladder because the wall is too high\n"
                    "Duration: 5"
                ]
            )
        )
    )
    troll.take_turn(game)
    # The record, fully populated:
    [wish] = game.wishes
    assert wish.actor == "troll"
    assert wish.desired == "build a ladder"
    assert wish.reason == "the wall is too high"
    # The streaming callback (what #622's backend will install):
    assert streamed == [wish]
    # The trace channel:
    [msg] = cap.by_channel(Channel.AGENT_WISH)
    assert msg.actor == "troll"
    # And the loop treated it as a successful action (no reflection retry):
    assert cap.by_channel(Channel.AGENT_REFLECTION) == []


# ----------------------------------------------------------------------
# Section G: parse-gap capture (#621) — the automatic trigger
# ----------------------------------------------------------------------


def test_unparseable_agent_command_records_parse_gap():
    game = tiny_game()
    troll = game.characters["troll"]
    assert not game.parser.parse_command("zibble the wumpus", actor=troll)
    [wish] = game.wishes
    assert wish.trigger == TRIGGER_PARSE_GAP
    assert wish.actor == "troll"
    assert wish.desired == "zibble the wumpus"
    assert wish.reason == ""
    assert wish.location == "Field"
    assert wish.raw_command == "zibble the wumpus"
    # The failure feedback is unchanged — the ReAct retry loop keeps working:
    assert game.parser.last_fail_message == "I'm not sure what you want to do."


def test_unparseable_player_command_records_parse_gap_too():
    game = tiny_game()
    assert not game.parser.parse_command("frobnicate")
    [wish] = game.wishes
    assert wish.actor == "player"
    assert wish.trigger == TRIGGER_PARSE_GAP


def test_successful_and_precondition_failed_commands_are_not_parse_gaps():
    game = tiny_game()
    troll = game.characters["troll"]
    game.parser.parse_command("go north", actor=troll)  # parses fine
    assert game.wishes == []
    game.parser.parse_command("propose", actor=troll)  # verb matched, gate failed
    assert game.wishes == []  # a precondition fail is NOT a parse gap


def test_craft_command_in_recipeless_game_is_still_a_parse_gap():
    # Option B (#628) guard: craft_gap is only reachable when the game has
    # registered recipes (parsing.py's CRAFT routing gate). tiny_game() never
    # registers any, so "make ..." never reaches CRAFT -- it falls through to
    # the no-verb gate and is captured the same way any other unmatched
    # command is, as a parse_gap, not a craft_gap. Same demand, different
    # trigger depending on whether the world happens to have crafting.
    game = tiny_game()
    assert not game.parser.parse_command("make boiled water")
    [wish] = game.wishes
    assert wish.trigger == TRIGGER_PARSE_GAP
    assert wish.desired == "make boiled water"


# ----------------------------------------------------------------------
# Section H: agent-only "none of these fit" in the LLM fallback (#621)
# ----------------------------------------------------------------------


def _numbered_options(messages):
    """The numbered option lines LlmParser._pick_option put in the system
    message, as (index, text) pairs (mirrors tests/test_agent_layer.py)."""
    import re

    lines = []
    for line in messages[0]["content"].splitlines():
        match = re.match(r"\s*(\d+)\.\s*(.*)", line)
        if match:
            lines.append((match.group(1), match.group(2)))
    return lines


def _force_mapping_llm(messages, max_tokens, temperature):
    """Simulates the pre-#621 reality: an LLM told to say which command the
    input 'most closely matches' always picks SOMETHING. It picks the decline
    option iff one is offered, else the first real option (a force-map)."""
    options = _numbered_options(messages)
    for index, text in options:
        if "none of these" in text.lower():
            return index
    return options[0][0] if options else None


def _pick_option_containing(keyword):
    """A responder that picks the first numbered option containing *keyword*."""

    def responder(messages, max_tokens, temperature):
        for index, text in _numbered_options(messages):
            if keyword.lower() in text.lower():
                return index
        return None

    return responder


def _llm_game(responder):
    from text_adventure_games.llm_client import MockLlmClient
    from text_adventure_games.llm_parser import WebLlmParser

    game = tiny_game()
    game.set_parser(WebLlmParser(game, MockLlmClient(responder)))
    return game


def test_agent_actor_can_decline_and_the_gap_is_captured():
    # Without the decline option, _force_mapping_llm maps "zibble the wumpus"
    # onto the first real command and it EXECUTES (the gap becomes noise).
    # With it, the agent-driven actor declines -> clean fail -> parse_gap wish.
    game = _llm_game(_force_mapping_llm)
    troll = game.characters["troll"]
    troll.set_agent(object())  # the Character.set_agent seam marks it agent-driven
    assert not game.parser.parse_command("zibble the wumpus", actor=troll)
    [wish] = game.wishes
    assert wish.trigger == TRIGGER_PARSE_GAP
    assert wish.actor == "troll"


def test_agent_actor_still_maps_real_paraphrases():
    game = _llm_game(_pick_option_containing("Go in a direction"))
    troll = game.characters["troll"]
    troll.set_agent(object())
    assert game.parser.determine_intent("vault the chasm", actor=troll) == "go"


def test_human_path_has_no_decline_option():
    captured = []

    def responder(messages, max_tokens, temperature):
        captured.append(messages[0]["content"])
        return None

    game = _llm_game(responder)
    game.parser.determine_intent("zibble the wumpus", actor=None)
    game.parser.determine_intent("zibble the wumpus", actor=game.player)
    assert captured and all("none of these" not in c.lower() for c in captured)


# ----------------------------------------------------------------------
# Section I: the native experimental parser honors the same seam (#621)
# ----------------------------------------------------------------------


def test_native_llm_parser_allows_decline_for_agent_actors_only():
    from text_adventure_games import parsing

    game = tiny_game()
    native = parsing.LlmParser.__new__(parsing.LlmParser)  # skip Anthropic init
    parsing.Parser.__init__(native, game, echo_commands=False)
    seen = []

    def fake_pick_one(instructions, options, query, allow_none=True):
        # Only record the INTENT pick: after it declines, the keyword-sniff
        # fallback consults the (also overridden) argument matchers, which
        # route through _pick_one too and would muddy the assertion.
        if "Choose the action" in instructions:
            seen.append(allow_none)
        return None

    native._pick_one = fake_pick_one
    troll = game.characters["troll"]
    native.determine_intent("zibble the wumpus", actor=troll)  # no agent
    troll.set_agent(object())
    native.determine_intent("zibble the wumpus", actor=troll)  # agent-driven
    assert seen == [False, True]


# ----------------------------------------------------------------------
# Section J: end-to-end — a ReAct agent's unparseable action becomes a wish
# ----------------------------------------------------------------------


def test_react_agent_parse_gap_flows_to_the_sink():
    from text_adventure_games.llm_client import MockLlmClient
    from text_adventure_games.npc import make_react_behavior

    game = tiny_game()
    troll = game.characters["troll"]
    streamed = []
    game.on_wish = streamed.append
    troll.set_behavior(
        make_react_behavior(
            MockLlmClient(
                [
                    "Reasoning: I will magic myself across\n"
                    "Action: zibble the wumpus\n"
                    "Duration: 5"
                ]
            )
        )
    )
    troll.take_turn(game)
    assert any(w.trigger == TRIGGER_PARSE_GAP for w in game.wishes)
    assert troll.location.name == "Field"  # nothing executed
    assert streamed  # the backend tap (#622) sees parse gaps too
