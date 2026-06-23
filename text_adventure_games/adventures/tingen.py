"""Tingen — a *Lord of the Mysteries* mystery, built on ``text_adventure_games``.

This is the engine-side of the Tingen game (issue #108): the world + the NPC
brains live here on the text-adventure engine; the Godot layer (under
``games/tingen/``) renders it. It is deliberately a vertical slice — enough to
prove the engine's core claim: **autonomous NPCs pursuing competing goals in a
shared world, who can be talked to**, gated by the classical precondition/effect
action model.

Setting: foggy Victorian Tingen City. A hidden cult is working a ritual to
summon an evil god from the crypt beneath Saint Selena's Cathedral. As the nights
pass the city's *corruption* rises; once it crests, the cult can complete the
rite. The player is Klein Moretti, a detective who must gather enough evidence
and reach the crypt to expose and stop them first.

Run it (free, offline scripted NPCs)::

    python -m text_adventure_games.adventures.tingen

Run it with LLM-driven NPC brains::

    LLM_PROVIDER=mock python -m text_adventure_games.adventures.tingen
    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... python -m text_adventure_games.adventures.tingen
"""

from text_adventure_games import games, things, actions
from text_adventure_games.things.characters import Goal, GoalType
from text_adventure_games.npc import make_hybrid_behavior

# Nights of rising corruption before the cult can complete the ritual. The cult
# reaches the crypt in ~2 turns then waits for the veil to thin; this window is
# tuned so a focused player (gather two clues -> reach the crypt -> expose) can
# beat them with a turn or two to spare, while idling loses the city.
RITUAL_THRESHOLD = 8
# Clues Klein must gather before he can expose the cult at the crypt.
CLUES_TO_EXPOSE = 2


class Tingen(games.Game):
    """The Tingen mystery. Won when Klein exposes the cult; lost if the cult
    completes the ritual first (the city falls)."""

    def __init__(self, start_at, player, characters=None, custom_actions=None):
        super().__init__(start_at, player, characters, custom_actions)
        # Tingen-specific world state (plain attributes; the engine's property
        # bag is bool-defaulted, so scalar world state lives here).
        self.corruption = 0
        self.clues_found = 0
        self.ritual_complete = False
        self.player_won = False

    def end_turn(self):
        """Each night the city festers a little more before the NPCs act."""
        self.corruption += 1
        super().end_turn()

    def is_won(self) -> bool:
        if self.player_won:
            self.parser.ok(
                "Klein lays the evidence bare beneath the cathedral. The rite "
                "collapses, the cultists scatter into the fog, and Tingen is "
                "spared. KLEIN HAS WON."
            )
            return True
        return False


# ---------------------------------------------------------------------------
# Tingen actions (precondition -> effect, like every engine action)
# ---------------------------------------------------------------------------


class Investigate(actions.Action):
    ACTION_NAME = "investigate"
    ACTION_DESCRIPTION = "Search the current location for a clue"
    ACTION_ALIASES = ["search", "search the area", "look for clues"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)

    def check_preconditions(self) -> bool:
        location = self.character.location
        if not location.get_property("has_clue"):
            self.parser.fail("There is nothing more to find here.")
            return False
        return True

    def apply_effects(self):
        location = self.character.location
        clue = location.get_property("clue_text") or "a fragment of evidence"
        location.set_property("has_clue", False)
        if self.character is self.game.player:
            self.game.clues_found += 1
        self.parser.ok(
            f"{self.character.name.title()} searches the {location.name} and finds: {clue}"
        )


class Perform_Ritual(actions.Action):
    ACTION_NAME = "perform ritual"
    ACTION_DESCRIPTION = "Complete the summoning rite (cultists only)"
    ACTION_ALIASES = ["complete ritual", "begin the rite"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)

    def check_preconditions(self) -> bool:
        if not self.has_property(
            self.character, "is_cultist", "Only the faithful may work the rite."
        ):
            return False
        if self.character.location.name != "Cathedral Crypt":
            self.parser.fail("The rite can only be worked in the crypt.")
            return False
        if self.game.corruption < RITUAL_THRESHOLD:
            self.parser.fail("The veil is not yet thin enough. Not tonight.")
            return False
        return True

    def apply_effects(self):
        self.game.ritual_complete = True
        self.game.game_over = True
        self.parser.ok(
            f"{self.character.name.title()} finishes the rite. The crypt fills with "
            "a cold that is not cold; something vast turns its attention toward "
            "Tingen. Klein was too late. THE CITY FALLS."
        )


class Expose_Cult(actions.Action):
    ACTION_NAME = "expose cult"
    ACTION_DESCRIPTION = "Confront the cult with your evidence to stop the rite"
    ACTION_ALIASES = ["expose the cult", "confront cult", "stop the ritual"]

    def __init__(self, game, command, actor=None):
        super().__init__(game, actor=actor)
        self.character = self.parser.get_character(command)

    def check_preconditions(self) -> bool:
        if self.character is not self.game.player:
            self.parser.fail("Only Klein can make the case.")
            return False
        if self.character.location.name != "Cathedral Crypt":
            self.parser.fail("The cult is gathered in the crypt, not here.")
            return False
        if self.game.clues_found < CLUES_TO_EXPOSE:
            self.parser.fail(
                "You lack the evidence to break their nerve. Find more first."
            )
            return False
        if self.game.ritual_complete:
            self.parser.fail(
                "The rite is already complete. There is nothing left to stop."
            )
            return False
        return True

    def apply_effects(self):
        self.game.player_won = True
        # is_won() narrates and ends the game.


# ---------------------------------------------------------------------------
# Scripted NPC behaviors (the free, offline fallback brains)
# ---------------------------------------------------------------------------


def make_cultist_leader_behavior():
    """Hanass advances to the crypt, then works the rite the moment the veil
    thins. A single-minded competing goal the player races against."""

    def behavior(character, game):
        if game.ritual_complete:
            return
        loc = character.location.name
        if loc == "Cathedral Crypt":
            if game.corruption >= RITUAL_THRESHOLD:
                game.parser.parse_command(f"{character.name} perform ritual")
            # else: wait in the dark for the veil to thin
        elif loc == "Saint Selena's Cathedral":
            game.parser.parse_command(f"{character.name} go down")
        elif loc == "Iron Cross Market":
            game.parser.parse_command(f"{character.name} go south")
        else:
            # Make for the market hub.
            game.parser.parse_command(f"{character.name} go east")

    return behavior


def make_patrol_behavior(stops):
    """A simple two-stop patrol (the Nighthawk and the acolyte pace the city)."""
    state = {"i": 0}

    def behavior(character, game):
        target = stops[state["i"] % len(stops)]
        state["i"] += 1
        direction = character.location.connections and _direction_to(character, target)
        if direction:
            game.parser.parse_command(f"{character.name} go {direction}")

    return behavior


def _direction_to(character, target_name):
    for direction, loc in character.location.connections.items():
        if loc.name == target_name:
            return direction
    return None


def make_idle_behavior():
    """Gravediggers and frightened civilians keep to themselves."""

    def behavior(character, game):
        return None

    return behavior


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def build_game(llm_client=None, embedding_client=None) -> Tingen:
    """Build the Tingen slice. With an ``llm_client`` the NPCs use the ReAct
    LLM brain (falling back to their scripted behavior on a failed turn); with
    none they run purely on the scripted behaviors above."""

    # --- Districts (from the canonical city map) ---
    market = things.Location(
        "Iron Cross Market",
        "The cobbled heart of the district. Fog curls between shuttered stalls; "
        "lamps hiss. Lanes run off in every direction.",
    )
    eel = things.Location(
        "The Laughing Eel",
        "A low, smoke-stained tavern. Dockers nurse their drinks and their secrets.",
    )
    coal_yard = things.Location(
        "Coal Yard",
        "Black hills of coal and the skeletons of cranes. Soot hangs in the air.",
    )
    cathedral = things.Location(
        "Saint Selena's Cathedral",
        "Twin Gothic spires above a hushed nave. A stair descends into the dark.",
    )
    crypt = things.Location(
        "Cathedral Crypt",
        "A vaulted undercroft of cold stone and older symbols. Something waits to be woken.",
    )
    cemetery = things.Location(
        "Raphael Cemetery",
        "Lopsided headstones under cypress and mist. One grave has been freshly disturbed.",
    )
    docks = things.Location(
        "Tingen Docks",
        "Tar, rope, and river-rot. Warehouses lean over the black water.",
    )
    hq = things.Location(
        "Blackthorn Security Co.",
        "The Nighthawks' front office. Case files, gaslight, and watchful eyes.",
    )

    # --- Connections (one graph centered on the market) ---
    market.add_connection("west", eel)
    market.add_connection("south", cathedral)
    market.add_connection("north", hq)
    market.add_connection("east", docks)
    eel.add_connection("north", coal_yard)
    cathedral.add_connection("down", crypt)
    cathedral.add_connection("west", cemetery)

    # --- Clues to gather (the investigation spine) ---
    docks.set_property("has_clue", True)
    docks.set_property(
        "clue_text",
        "a bloodstained shipping ledger naming a midnight cargo to the cathedral.",
    )
    cemetery.set_property("has_clue", True)
    cemetery.set_property(
        "clue_text",
        "an empty grave and cult sigils scratched into the headstone.",
    )
    eel.set_property("has_clue", True)
    eel.set_property(
        "clue_text",
        "a terrified witness who saw robed figures carry someone toward Selena's.",
    )
    cathedral.set_property("has_clue", True)
    cathedral.set_property(
        "clue_text",
        "candle wax, chalk sigils, and a trapdoor to the crypt behind the altar.",
    )

    # --- The player: Klein ---
    player = things.Character(
        name="Klein",
        description="A composed young detective in a charcoal coat.",
        persona="I am Klein Moretti. People are vanishing into the fog. I will find "
        "the evidence, follow it to its source, and stop whatever is being done "
        "beneath the cathedral.",
    )
    player.set_property("character_type", "human")

    # --- The cult leader: competing LONG goal, races to the crypt ---
    hanass = things.Character(
        name="Hanass",
        description="A gaunt man with a fixed, patient smile.",
        persona="I am the one who opens the way. The others are sheep; I am the "
        "shepherd. Tonight, beneath Saint Selena's, the veil thins and our god "
        "will wake. Nothing must stand in the way of the rite.",
        goals=[
            Goal("Complete the summoning rite in the crypt", GoalType.LONG),
            Goal("Reach the cathedral crypt before dawn", GoalType.MEDIUM),
        ],
    )
    hanass.set_property("character_type", "human")
    hanass.set_property("is_cultist", True)
    hanass.talk_text = '"Lost, detective? The fog takes everyone eventually."'
    hanass.talk_topics = {
        "ritual": '"Ritual? You mistake worship for superstition."',
        "cult": '"There is no cult. Only the faithful, and the blind."',
    }

    # --- The acolyte: serves the cult, paces between docks and market ---
    acolyte = things.Character(
        name="acolyte",
        description="A nervous figure with ink-stained fingers and a hidden sigil.",
        persona="I run errands for the master and tell no one. I move the cargo, "
        "I watch the streets, and I keep the Nighthawks looking the wrong way.",
        goals=[Goal("Cover the cult's tracks", GoalType.MEDIUM)],
    )
    acolyte.set_property("character_type", "human")
    acolyte.set_property("is_cultist", True)

    # --- The ally: Nighthawk captain, investigating in parallel ---
    dunn = things.Character(
        name="Dunn",
        description="A broad Nighthawk captain who has seen too much.",
        persona="I am Captain Dunn of the Nighthawks. Five gone this month and the "
        "Church says nothing. If the detective has evidence, I will listen.",
        goals=[Goal("Investigate the disappearances", GoalType.MEDIUM)],
    )
    dunn.set_property("character_type", "human")
    dunn.talk_text = (
        '"Klein. Bring me proof, not ghost stories, and I will move on them."'
    )
    dunn.talk_topics = {
        "cult": '"Robes and candles in the old crypt. I need evidence to act."',
        "ritual": '"If they finish whatever they are doing, this city is finished too."',
    }

    # --- A civilian rumor-source at the cemetery ---
    gravedigger = things.Character(
        name="gravedigger",
        description="A stooped man with a lantern and a loose tongue.",
        persona="I dig the graves nobody asks about. I see who comes at night, and "
        "I will tell a kind listener what the headstones cannot.",
    )
    gravedigger.set_property("character_type", "human")
    gravedigger.talk_text = (
        '"Fresh grave, emptied by morning. They went toward Selena\'s."'
    )
    gravedigger.talk_topics = {
        "grave": '"Dug it Tuesday. Empty by Thursday. No coffin walks off on its own."',
    }

    # --- Place characters ---
    market.add_character(hanass)
    docks.add_character(acolyte)
    hq.add_character(dunn)
    cemetery.add_character(gravedigger)

    # --- Wire NPC brains: scripted fallback always; LLM on top when provided ---
    scripted = {
        hanass: make_cultist_leader_behavior(),
        acolyte: make_patrol_behavior(["Iron Cross Market", "Tingen Docks"]),
        dunn: make_patrol_behavior(["Iron Cross Market", "Blackthorn Security Co."]),
        gravedigger: make_idle_behavior(),
    }
    for character, fallback in scripted.items():
        if llm_client is not None:
            character.set_behavior(
                make_hybrid_behavior(
                    llm_client, fallback, embedding_client=embedding_client
                )
            )
        else:
            character.set_behavior(fallback)

    custom_actions = [Investigate, Perform_Ritual, Expose_Cult]
    characters = [hanass, acolyte, dunn, gravedigger]
    return Tingen(market, player, characters, custom_actions)


if __name__ == "__main__":
    from text_adventure_games.llm_client import client_from_env

    game = build_game(llm_client=client_from_env())
    game.game_loop()
