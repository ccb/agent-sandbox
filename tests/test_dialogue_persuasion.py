"""Offline tests for goal-influencing dialogue / persuasion (issue #46).

A speaker's utterance reaches only co-located listeners (the `heard` buffer,
scoped by Game.audience_for); a listener's LLM agent may then adopt or drop a
goal through the normal precondition gate. Driven by the deterministic
MockReActClient so the whole thing runs offline and for free.
"""

from text_adventure_games import games, things
from text_adventure_games.things.characters import Character, GoalType, HEARD_MAX


def test_hear_appends_and_trims_to_cap():
    c = Character("bob", "a fellow", "I listen.")
    for i in range(HEARD_MAX + 3):
        c.hear(f"line {i}")
    assert len(c.heard) == HEARD_MAX
    # The three oldest entries (0, 1, 2) were dropped; newest is kept.
    assert c.heard[0] == "line 3"
    assert c.heard[-1] == f"line {HEARD_MAX + 2}"


def test_clear_heard_empties_buffer():
    c = Character("bob", "a fellow", "I listen.")
    c.hear("something")
    c.clear_heard()
    assert c.heard == []


def test_audience_for_co_located_minus_speaker():
    field = things.Location("Field", "A field.")
    alice = things.Character("alice", "a herald", "I speak.")
    bob = things.Character("bob", "a fellow", "I listen.")
    game = games.Game(field, alice, characters=[bob])
    field.add_character(bob)

    audience = game.audience_for(alice, "hello", bob)
    assert bob in audience
    assert alice not in audience  # speaker never hears self


def test_audience_for_excludes_other_room():
    field = things.Location("Field", "A field.")
    forest = things.Location("Forest", "A forest.")
    field.add_connection("north", forest)
    alice = things.Character("alice", "a herald", "I speak.")
    carol = things.Character("carol", "afar", "I am elsewhere.")
    game = games.Game(field, alice, characters=[carol])
    forest.add_character(carol)  # not co-located with alice

    assert game.audience_for(alice, "hello") == []


def _two_char_room():
    """alice (player/speaker) and bob (listener), co-located in a field."""
    field = things.Location("Field", "A field.")
    alice = things.Character("alice", "a herald", "I speak.")
    bob = things.Character("bob", "a fellow", "I listen.")
    game = games.Game(field, alice, characters=[bob])
    field.add_character(bob)
    return game, alice, bob


def test_directed_speech_heard_as_to_you():
    game, alice, bob = _two_char_room()
    game.parser.parse_command("say to bob fetch the key", actor=alice)
    assert bob.heard == ["alice said to you: fetch the key"]


def test_broadcast_speech_heard_plainly():
    game, alice, bob = _two_char_room()
    game.parser.parse_command("say hello everyone", actor=alice)
    assert bob.heard == ["alice said: hello everyone"]


def test_speaker_does_not_hear_self():
    game, alice, bob = _two_char_room()
    game.parser.parse_command("say hello", actor=alice)
    assert alice.heard == []


def test_bystander_overhears_directed_speech():
    field = things.Location("Field", "A field.")
    alice = things.Character("alice", "a herald", "I speak.")
    bob = things.Character("bob", "a fellow", "I listen.")
    carol = things.Character("carol", "a bystander", "I overhear.")
    game = games.Game(field, alice, characters=[bob, carol])
    field.add_character(bob)
    field.add_character(carol)
    game.parser.parse_command("say to bob secret plan", actor=alice)
    assert carol.heard == ["alice said to bob: secret plan"]


def test_other_room_does_not_hear_broadcast():
    field = things.Location("Field", "A field.")
    forest = things.Location("Forest", "A forest.")
    field.add_connection("north", forest)
    alice = things.Character("alice", "a herald", "I speak.")
    carol = things.Character("carol", "afar", "I am elsewhere.")
    game = games.Game(field, alice, characters=[carol])
    forest.add_character(carol)
    game.parser.parse_command("say hello", actor=alice)
    assert carol.heard == []


from text_adventure_games.actions.goals import AdoptGoal, DropGoal


def _solo_game():
    """A single character (used as the player) in a field."""
    field = things.Location("Field", "A field.")
    bob = things.Character("bob", "a fellow", "I listen.")
    game = games.Game(field, bob)
    return game, bob


def test_adopt_goal_adds_short_goal():
    game, bob = _solo_game()
    AdoptGoal(game, "adopt goal fetch the key", actor=bob)()
    assert any(
        g.description == "fetch the key" and g.type == GoalType.SHORT and not g.done
        for g in bob.goals
    )


def test_adopt_goal_empty_text_fails():
    game, bob = _solo_game()
    action = AdoptGoal(game, "adopt goal", actor=bob)
    assert action.check_preconditions() is False
    assert bob.goals == []


def test_adopt_goal_duplicate_fails():
    game, bob = _solo_game()
    bob.add_goal("fetch the key", GoalType.SHORT)
    action = AdoptGoal(game, "adopt goal fetch the key", actor=bob)
    assert action.check_preconditions() is False
    assert len(bob.goals) == 1


def test_drop_goal_removes_it():
    game, bob = _solo_game()
    bob.add_goal("fetch the key", GoalType.SHORT)
    DropGoal(game, "drop goal fetch the key", actor=bob)()
    assert bob.goals == []


def test_drop_goal_not_held_fails():
    game, bob = _solo_game()
    action = DropGoal(game, "drop goal nonexistent", actor=bob)
    assert action.check_preconditions() is False


def test_determine_intent_routes_goal_verbs():
    game, bob = _solo_game()
    p = game.parser
    # "drop goal ..." must NOT be hijacked by the inventory "drop" verb.
    assert p.determine_intent("drop goal fetch the key", actor=bob) == "drop goal"
    assert p.determine_intent("adopt goal fetch the key", actor=bob) == "adopt goal"
    # A plain "drop <item>" still routes to inventory drop.
    assert p.determine_intent("drop sword", actor=bob) == "drop"


def test_parse_command_adopt_goal_end_to_end():
    game, bob = _solo_game()
    assert game.parser.parse_command("adopt goal fetch the key", actor=bob)
    assert any(g.description == "fetch the key" for g in bob.goals)


def test_parse_command_drop_goal_end_to_end():
    game, bob = _solo_game()
    bob.add_goal("fetch the key", GoalType.SHORT)
    assert game.parser.parse_command("drop goal fetch the key", actor=bob)
    assert bob.goals == []


from text_adventure_games.npc import build_npc_context


def test_build_npc_context_renders_heard_and_note():
    game, alice, bob = _two_char_room()
    bob.hear("alice said to you: fetch the key")
    obs = build_npc_context(bob, game)
    assert "You recently heard:" in obs
    assert "alice said to you: fetch the key" in obs
    # The optional-input note keeps persuasion non-automatic.
    assert "only adopt or drop a goal" in obs


def test_build_npc_context_omits_heard_when_empty():
    game, alice, bob = _two_char_room()
    obs = build_npc_context(bob, game)
    assert "You recently heard:" not in obs


from text_adventure_games.llm_client import _mock_brain_choose
from text_adventure_games.npc import _parse_decision


def _action_of(reply):
    """The command from a labeled 'Reasoning: ...\\nAction: ...' mock reply."""
    return _parse_decision(reply)[1]


SERVANT_SYSTEM = (
    "You are an NPC in a text adventure game.\n"
    "Persona: I am the servant. I live to serve my master."
)
REQUEST_OBS = (
    "FIELD\nA field.\n"
    "You recently heard:\n"
    "  - master said to you: please fetch the golden key\n"
)


def test_mock_brain_servant_adopts_on_request():
    reply = _mock_brain_choose(SERVANT_SYSTEM, REQUEST_OBS)
    assert _action_of(reply) == "adopt goal fetch the golden key"


def test_mock_brain_servant_silent_without_request():
    assert _mock_brain_choose(SERVANT_SYSTEM, "FIELD\nA field.\n") is None


def test_mock_brain_servant_does_not_readopt_when_goal_held():
    system = SERVANT_SYSTEM + "\nGoals:\nShort-term:\n  - fetch the golden key"
    assert _mock_brain_choose(system, REQUEST_OBS) is None


def test_mock_brain_stubborn_knight_refuses():
    system = (
        "You are an NPC in a text adventure game.\n"
        "Persona: I am the stubborn knight. I serve no one."
    )
    assert _mock_brain_choose(system, REQUEST_OBS) is None


from text_adventure_games.llm_client import MockReActClient
from text_adventure_games.npc import make_react_behavior


def _persuasion_scene(name, persona):
    """A field with `master` (player/speaker) and one agent-driven NPC."""
    field = things.Location("Field", "A grassy field.")
    master = things.Character("master", "a noble", "I command my servants.")
    npc = things.Character(name, "a retainer", persona)
    game = games.Game(field, master, characters=[npc])
    field.add_character(npc)
    mock = MockReActClient()
    npc.set_behavior(make_react_behavior(mock))
    return game, master, npc, mock


def test_servant_adopts_goal_after_hearing_request():
    game, master, servant, mock = _persuasion_scene(
        "servant", "I am the servant. I live to serve my master."
    )
    # The master speaks; do_command runs the player's say, then end_turn()
    # gives the servant its turn -- on which it hears the request and adopts.
    game.do_command("say to servant please fetch the golden key")
    assert any("fetch the golden key" in g.description for g in servant.goals)
    # The servant actually took a decision on its turn (rather than the goal
    # having somehow pre-existed): the brain recorded a non-None command.
    assert mock.tool_calls


def test_stubborn_knight_does_not_adopt():
    game, master, knight, mock = _persuasion_scene(
        "knight", "I am the stubborn knight. I serve no one."
    )
    game.do_command("say to knight please fetch the golden key")
    assert knight.goals == []


def test_listener_in_other_room_never_hears():
    field = things.Location("Field", "A grassy field.")
    hall = things.Location("Hall", "A stone hall.")
    field.add_connection("north", hall)
    master = things.Character("master", "a noble", "I command my servants.")
    servant = things.Character(
        "servant", "a retainer", "I am the servant. I live to serve my master."
    )
    game = games.Game(field, master, characters=[servant])
    hall.add_character(servant)  # another room
    mock = MockReActClient()
    servant.set_behavior(make_react_behavior(mock))

    # A broadcast in the field reaches only the field; the servant is in the
    # hall, so it hears nothing and adopts no goal even though it takes a turn.
    game.do_command("say please fetch the golden key")
    assert servant.heard == []
    assert servant.goals == []
