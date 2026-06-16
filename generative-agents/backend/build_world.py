"""Build the Smallville world as a ``text_adventure_games`` game.

This is the "uses our library" half of the port: Smallville's places become
engine ``Location``s, the cast become ``Character``s carrying first-person
persona text (lifted from the upstream ``scratch.json`` profiles), and the two
custom actions (:mod:`actions`) are registered so agents can ``travel`` and
``perform`` through the normal precondition gate.

The world is intentionally small for v1 -- the three canonical demo agents and
the handful of places their morning routine touches -- but the structure
(persona metadata + location tile addresses) is data-driven and easy to grow.
"""

from text_adventure_games import games
from text_adventure_games.things.characters import Character
from text_adventure_games.things.locations import Location

from .actions import Act, Travel

# The cast. `persona` is the first-person identity the agent reasons as (drawn
# from the base sim's scratch.json). `home`/`start_tile` set where each agent
# wakes; `destination`/`activity`/`emoji` are their morning goal -- where they
# head and what they do when they arrive. `start_tile` matches the upstream base
# simulation's environment/0.json so the frontend places them exactly as it does.
PERSONAS = [
    {
        "name": "Isabella Rodriguez",
        "home": "Isabella Rodriguez's apartment",
        "persona": (
            "I am Isabella Rodriguez, 34. I am friendly, outgoing, and "
            "hospitable. I own Hobbs Cafe and love making people feel welcome."
        ),
        "destination": "Hobbs Cafe",
        "activity": "tending the cafe counter",
        "emoji": "☕",  # coffee
        "start_tile": (72, 14),
    },
    {
        "name": "Maria Lopez",
        "home": "Dorm for Oak Hill College",
        "persona": (
            "I am Maria Lopez, 21. I am energetic, enthusiastic, and "
            "inquisitive. I study physics at Oak Hill College and spend most "
            "days studying at Hobbs Cafe."
        ),
        "destination": "Hobbs Cafe",
        "activity": "studying at a cafe table",
        "emoji": "\U0001f4da",  # books
        "start_tile": (123, 57),
    },
    {
        "name": "Klaus Mueller",
        "home": "Dorm for Oak Hill College",
        "persona": (
            "I am Klaus Mueller, 20. I am kind, inquisitive, and passionate. "
            "I study sociology at Oak Hill College and am writing a research "
            "paper in the college library."
        ),
        "destination": "Oak Hill College",
        "activity": "writing a research paper",
        "emoji": "✍️",  # writing hand
        "start_tile": (126, 46),
    },
]

# Engine locations. Each maps to a Smallville tile address so the exporter can
# resolve a walking target. Homes need an address only for flavor; the two
# destinations' arena addresses are where agents actually path to.
_LOCATIONS = [
    {
        "name": "the Ville",
        "description": "The streets of Smallville, tying every corner of town together.",
        "address": None,
        "hub": True,
    },
    {
        "name": "Isabella Rodriguez's apartment",
        "description": "Isabella's cozy apartment above the cafe district.",
        "address": "the Ville:Isabella Rodriguez's apartment:main room",
    },
    {
        "name": "Dorm for Oak Hill College",
        "description": "The Oak Hill College dorm where the students live.",
        "address": "the Ville:Dorm for Oak Hill College",
    },
    {
        "name": "Hobbs Cafe",
        "description": "A warm neighborhood cafe -- the social heart of Smallville.",
        "address": "the Ville:Hobbs Cafe:cafe",
    },
    {
        "name": "Oak Hill College",
        "description": "The local college; its library is a quiet place to study and write.",
        "address": "the Ville:Oak Hill College:library",
    },
]


def build_world():
    """Construct the Smallville game.

    Returns ``(game, characters)`` where ``characters`` maps persona name ->
    :class:`Character`. Agents are *not* attached here (see
    :mod:`smallville_agents`); the caller wires those onto each character.
    """
    locations: dict[str, Location] = {}
    hub = None
    for spec in _LOCATIONS:
        loc = Location(spec["name"], spec["description"])
        # Plain attribute (not a bool property): the Smallville address this
        # engine location resolves to on the tile map.
        loc.tile_address = spec["address"]
        locations[spec["name"]] = loc
        if spec.get("hub"):
            hub = spec["name"]

    # Wire every location to the hub so Game.__init__ discovers them all (it
    # walks the connection graph from start_at). Non-canonical direction labels
    # ("to hobbs cafe") don't auto-create a reverse exit, which is fine: agents
    # travel by name via the Travel action, not by compass direction.
    hub_loc = locations[hub]
    for name, loc in locations.items():
        if name != hub:
            hub_loc.add_connection(f"to {name.lower()}", loc)

    # A silent observer stands in as the engine's required "player". It never
    # acts; all three personas are NPCs driven by their agents.
    observer = Character(
        "Observer", "A silent observer of the town.", "I quietly watch Smallville."
    )

    characters: dict[str, Character] = {}
    for spec in PERSONAS:
        char = Character(spec["name"], spec["name"], spec["persona"])
        characters[spec["name"]] = char

    game = games.Game(
        hub_loc,
        observer,
        characters=list(characters.values()),
        custom_actions=[Travel, Act],
        turn_mode="simultaneous",
    )

    # Place each persona in their home location (Game only auto-places the player).
    for spec in PERSONAS:
        locations[spec["home"]].add_character(characters[spec["name"]])

    return game, characters
