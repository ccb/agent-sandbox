"""Build the Smallville world as a ``text_adventure_games`` game.

This is the "uses our library" half of the port: Smallville's places become
engine ``Location``s, the cast become ``Character``s carrying first-person
persona text (lifted from the upstream ``scratch.json`` profiles), and the two
custom actions (:mod:`actions`) are registered so agents can ``travel`` and
``perform`` through the normal precondition gate.

The world is fully data-driven: every persona is one entry in :data:`PERSONAS`
and every place one entry in :data:`_LOCATIONS`. We model the whole upstream
``the_ville_n25`` cast -- all 25 residents -- each waking at home and heading to
where they spend their day (the cafe owner to her cafe, students to the college,
the bartender to the pub, and so on). Adding a 26th resident is just another
dict; adding a new place is one more location.
"""

from text_adventure_games import games
from text_adventure_games.things.characters import Character
from text_adventure_games.things.locations import Location

from .actions import Act, Travel

# The cast -- the full 25-resident "the ville" town from the upstream base sim.
# Each entry is one persona:
#   name        display name (also picks the sprite: "John Lin" -> John_Lin.png)
#   home        the location they wake in (must be a name in _LOCATIONS)
#   persona     the first-person identity the agent reasons as (innate traits +
#               background, condensed from the upstream scratch.json profile)
#   destination where they head for the day (must be a name in _LOCATIONS)
#   activity    what they do once they arrive (the on-screen action label)
#   emoji       the pronunciatio bubble shown above the sprite while performing
#   start_tile  the (x, y) tile they spawn on -- matches the base sim's
#               environment/0.json so the frontend places them exactly as upstream
#
# Grouped by neighborhood for readability; order does not matter to the engine.
PERSONAS = [
    # -- The cafe & the college (north / east of town) ----------------------
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
    {
        "name": "Ayesha Khan",
        "home": "Dorm for Oak Hill College",
        "persona": (
            "I am Ayesha Khan, 20. I am curious, determined, and independent. "
            "I study literature at Oak Hill College and research Shakespeare "
            "in the library."
        ),
        "destination": "Oak Hill College",
        "activity": "studying in the library",
        "emoji": "\U0001f4d6",  # open book
        "start_tile": (118, 61),
    },
    {
        "name": "Wolfgang Schulz",
        "home": "Dorm for Oak Hill College",
        "persona": (
            "I am Wolfgang Schulz, 21. I am hardworking, passionate, and "
            "dedicated. I study chemistry at Oak Hill College and I am a "
            "student athlete who trains every morning."
        ),
        "destination": "Johnson Park",
        "activity": "going for a morning run",
        "emoji": "\U0001f3c3",  # runner
        "start_tile": (107, 62),
    },
    {
        "name": "Eddy Lin",
        "home": "Lin family's house",
        "persona": (
            "I am Eddy Lin, 19. I am curious, analytical, and musical. I study "
            "music theory and composition at Oak Hill College."
        ),
        "destination": "Oak Hill College",
        "activity": "working on a music composition",
        "emoji": "\U0001f3b5",  # musical note
        "start_tile": (93, 74),
    },
    {
        "name": "Mei Lin",
        "home": "Lin family's house",
        "persona": (
            "I am Mei Lin, 44. I am nurturing, kind, and patient. I am a "
            "college professor teaching philosophy at Oak Hill College."
        ),
        "destination": "Oak Hill College",
        "activity": "teaching a class",
        "emoji": "\U0001f3eb",  # school
        "start_tile": (90, 74),
    },
    {
        "name": "Giorgio Rossi",
        "home": "Giorgio Rossi's apartment",
        "persona": (
            "I am Giorgio Rossi, 41. I am analytical, logical, and eccentric. "
            "I am a mathematician who loves solving challenging problems."
        ),
        "destination": "Oak Hill College",
        "activity": "working on a math problem",
        "emoji": "➗",  # heavy division sign
        "start_tile": (86, 18),
    },
    {
        "name": "Yuriko Yamamoto",
        "home": "Yuriko Yamamoto's house",
        "persona": (
            "I am Yuriko Yamamoto, 28. I am organized, reliable, and "
            "detail-oriented. I am a tax lawyer who helps people navigate "
            "the complex world of taxes."
        ),
        "destination": "Oak Hill College",
        "activity": "reviewing tax filings",
        "emoji": "\U0001f4d1",  # bookmark tabs
        "start_tile": (28, 65),
    },
    # -- The pharmacy, the shops & the pub ----------------------------------
    {
        "name": "John Lin",
        "home": "Lin family's house",
        "persona": (
            "I am John Lin, 45. I am patient, kind, and organized. I keep the "
            "pharmacy counter at the Willows Market and Pharmacy and love "
            "helping people get the medication they need."
        ),
        "destination": "The Willows Market and Pharmacy",
        "activity": "running the pharmacy counter",
        "emoji": "\U0001f48a",  # pill
        "start_tile": (91, 74),
    },
    {
        "name": "Tom Moreno",
        "home": "Moreno family's house",
        "persona": (
            "I am Tom Moreno, 52. I am energetic and blunt. I keep the grocery "
            "counter at the Willows Market and Pharmacy and like looking after "
            "my customers."
        ),
        "destination": "The Willows Market and Pharmacy",
        "activity": "running the grocery counter",
        "emoji": "\U0001f6d2",  # shopping cart
        "start_tile": (73, 74),
    },
    {
        "name": "Jane Moreno",
        "home": "Moreno family's house",
        "persona": (
            "I am Jane Moreno, 46. I am friendly, helpful, and organized. I "
            "look after my family and home, and I am married to Tom Moreno."
        ),
        "destination": "The Willows Market and Pharmacy",
        "activity": "doing the grocery shopping",
        "emoji": "\U0001f6cd",  # shopping bags
        "start_tile": (72, 74),
    },
    {
        "name": "Carmen Ortiz",
        "home": "Tamara Taylor and Carmen Ortiz's house",
        "persona": (
            "I am Carmen Ortiz, 33. I am friendly, outgoing, and helpful. I "
            "run Harvey Oak Supply Store and love helping people find the "
            "supplies they need."
        ),
        "destination": "Harvey Oak Supply Store",
        "activity": "minding the supply store",
        "emoji": "\U0001f527",  # wrench
        "start_tile": (57, 74),
    },
    {
        "name": "Arthur Burton",
        "home": "Arthur Burton's apartment",
        "persona": (
            "I am Arthur Burton, 42. I am friendly, outgoing, and generous. I "
            "own The Rose and Crown Pub and love making my customers feel "
            "welcome."
        ),
        "destination": "The Rose and Crown Pub",
        "activity": "tending the bar",
        "emoji": "\U0001f37a",  # beer
        "start_tile": (53, 14),
    },
    # -- Hobbs Cafe regulars (artists, writers, the software engineer) ------
    {
        "name": "Ryan Park",
        "home": "Ryan Park's apartment",
        "persona": (
            "I am Ryan Park, 29. I am analytical, pragmatic, and driven. I am "
            "a software engineer building a new mobile app."
        ),
        "destination": "Hobbs Cafe",
        "activity": "coding a mobile app",
        "emoji": "\U0001f4bb",  # laptop
        "start_tile": (65, 19),
    },
    {
        "name": "Adam Smith",
        "home": "Adam Smith's house",
        "persona": (
            "I am Adam Smith, 36. I am thoughtful, reflective, and "
            "intellectual. I am a philosopher writing a book about the "
            "importance of creativity."
        ),
        "destination": "Hobbs Cafe",
        "activity": "writing his book over coffee",
        "emoji": "\U0001f4d8",  # blue book
        "start_tile": (20, 65),
    },
    {
        "name": "Abigail Chen",
        "home": "artist's co-living space",
        "persona": (
            "I am Abigail Chen, 25. I am open-minded, curious, and determined. "
            "I am a digital artist and animator exploring how technology can "
            "express ideas."
        ),
        "destination": "Hobbs Cafe",
        "activity": "working on an animation",
        "emoji": "\U0001f3a8",  # artist palette
        "start_tile": (36, 18),
    },
    {
        "name": "Hailey Johnson",
        "home": "artist's co-living space",
        "persona": (
            "I am Hailey Johnson, 30. I am imaginative, energetic, and "
            "resourceful. I am a writer working on a novel about artists "
            "living in a co-living space."
        ),
        "destination": "Hobbs Cafe",
        "activity": "writing her novel",
        "emoji": "\U0001f4dd",  # memo
        "start_tile": (26, 32),
    },
    {
        "name": "Tamara Taylor",
        "home": "Tamara Taylor and Carmen Ortiz's house",
        "persona": (
            "I am Tamara Taylor, 30. I am imaginative, patient, and kind. I am "
            "a children's book author working on a new series."
        ),
        "destination": "Hobbs Cafe",
        "activity": "writing a children's book",
        "emoji": "✏️",  # pencil
        "start_tile": (54, 74),
    },
    # -- Johnson Park crowd (poet, painters, the retired officer) -----------
    {
        "name": "Carlos Gomez",
        "home": "Carlos Gomez's apartment",
        "persona": (
            "I am Carlos Gomez, 32. I am loud, opinionated, and provocative. "
            "I am a poet exploring the beauty of the natural world."
        ),
        "destination": "Johnson Park",
        "activity": "writing poetry in the park",
        "emoji": "✒️",  # fountain pen
        "start_tile": (94, 18),
    },
    {
        "name": "Francisco Lopez",
        "home": "artist's co-living space",
        "persona": (
            "I am Francisco Lopez, 23. I am outgoing, friendly, and honest. I "
            "am an actor and comedian who loves to make people laugh."
        ),
        "destination": "Johnson Park",
        "activity": "rehearsing a comedy routine",
        "emoji": "\U0001f3ad",  # performing arts
        "start_tile": (16, 32),
    },
    {
        "name": "Latoya Williams",
        "home": "artist's co-living space",
        "persona": (
            "I am Latoya Williams, 25. I am organized, logical, and attentive. "
            "I am a digital photographer creating a series inspired by my "
            "travels."
        ),
        "destination": "Johnson Park",
        "activity": "photographing the park",
        "emoji": "\U0001f4f7",  # camera
        "start_tile": (16, 18),
    },
    {
        "name": "Rajiv Patel",
        "home": "artist's co-living space",
        "persona": (
            "I am Rajiv Patel, 27. I am patient, reliable, and cheerful. I am "
            "a painter preparing for my first solo show."
        ),
        "destination": "Johnson Park",
        "activity": "painting at the park",
        "emoji": "\U0001f5bc",  # framed picture
        "start_tile": (26, 18),
    },
    {
        "name": "Jennifer Moore",
        "home": "Moore family's house",
        "persona": (
            "I am Jennifer Moore, 68. I am wise, experienced, and warm. I am a "
            "watercolor painter of fifty years preparing for an exhibition."
        ),
        "destination": "Johnson Park",
        "activity": "painting watercolors",
        "emoji": "\U0001f58c",  # paintbrush
        "start_tile": (37, 65),
    },
    {
        "name": "Sam Moore",
        "home": "Moore family's house",
        "persona": (
            "I am Sam Moore, 65. I am wise, resourceful, and humorous. I am a "
            "retired navy officer who tends Johnson Park and is running for "
            "local mayor."
        ),
        "destination": "Johnson Park",
        "activity": "strolling around the park",
        "emoji": "\U0001f333",  # tree
        "start_tile": (36, 65),
    },
]

# Engine locations. Each maps to a Smallville tile address so the exporter can
# resolve a walking target. Homes need an address only for flavor (the morning
# "waking up @ ..." label); the day destinations' arena addresses are where
# agents actually path to.
_LOCATIONS = [
    {
        "name": "the Ville",
        "description": "The streets of Smallville, tying every corner of town together.",
        "address": None,
        "hub": True,
    },
    # -- Homes (where the cast wakes) ---------------------------------------
    {
        "name": "Isabella Rodriguez's apartment",
        "description": "Isabella's cozy apartment above the cafe district.",
        "address": "the Ville:Isabella Rodriguez's apartment:main room",
    },
    {
        "name": "Dorm for Oak Hill College",
        "description": "The Oak Hill College dorm where the students live.",
        "address": "the Ville:Dorm for Oak Hill College:common room",
    },
    {
        "name": "artist's co-living space",
        "description": "A shared house where the town's artists and writers live.",
        "address": "the Ville:artist's co-living space:common room",
    },
    {
        "name": "Lin family's house",
        "description": "The Lin family home, where John, Mei, and Eddy live.",
        "address": "the Ville:Lin family's house:common room",
    },
    {
        "name": "Moreno family's house",
        "description": "The Moreno family home, where Tom and Jane live.",
        "address": "the Ville:Moreno family's house:common room",
    },
    {
        "name": "Moore family's house",
        "description": "The Moore family home, where Sam and Jennifer live.",
        "address": "the Ville:Moore family's house:main room",
    },
    {
        "name": "Tamara Taylor and Carmen Ortiz's house",
        "description": "The house Tamara and Carmen share.",
        "address": "the Ville:Tamara Taylor and Carmen Ortiz's house:common room",
    },
    {
        "name": "Adam Smith's house",
        "description": "Adam Smith's quiet house, lined with books.",
        "address": "the Ville:Adam Smith's house:main room",
    },
    {
        "name": "Arthur Burton's apartment",
        "description": "Arthur Burton's apartment near the pub.",
        "address": "the Ville:Arthur Burton's apartment:main room",
    },
    {
        "name": "Carlos Gomez's apartment",
        "description": "Carlos Gomez's apartment.",
        "address": "the Ville:Carlos Gomez's apartment:main room",
    },
    {
        "name": "Giorgio Rossi's apartment",
        "description": "Giorgio Rossi's apartment.",
        "address": "the Ville:Giorgio Rossi's apartment:main room",
    },
    {
        "name": "Ryan Park's apartment",
        "description": "Ryan Park's apartment.",
        "address": "the Ville:Ryan Park's apartment:main room",
    },
    {
        "name": "Yuriko Yamamoto's house",
        "description": "Yuriko Yamamoto's house.",
        "address": "the Ville:Yuriko Yamamoto's house:main room",
    },
    # -- Day destinations (the public places the cast heads to) -------------
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
    {
        "name": "Johnson Park",
        "description": "The town's green park, good for a walk or a quiet read.",
        "address": "the Ville:Johnson Park:park",
    },
    {
        "name": "The Willows Market and Pharmacy",
        "description": "The town market and pharmacy, with a grocery and a medicine counter.",
        "address": "the Ville:The Willows Market and Pharmacy:store",
    },
    {
        "name": "Harvey Oak Supply Store",
        "description": "The general supply store run by Carmen Ortiz.",
        "address": "the Ville:Harvey Oak Supply Store:supply store",
    },
    {
        "name": "The Rose and Crown Pub",
        "description": "Arthur Burton's beloved pub, a decade-old town fixture.",
        "address": "the Ville:The Rose and Crown Pub:pub",
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

    # Catch a typo in a persona's home/destination early, with a clear message,
    # rather than failing deep inside the parser at simulate() time.
    for spec in PERSONAS:
        for key in ("home", "destination"):
            if spec[key] not in locations:
                raise ValueError(
                    f"{spec['name']}'s {key} '{spec[key]}' is not a known location"
                )

    # Wire every location to the hub so Game.__init__ discovers them all (it
    # walks the connection graph from start_at). Non-canonical direction labels
    # ("to hobbs cafe") don't auto-create a reverse exit, which is fine: agents
    # travel by name via the Travel action, not by compass direction.
    hub_loc = locations[hub]
    for name, loc in locations.items():
        if name != hub:
            hub_loc.add_connection(f"to {name.lower()}", loc)

    # A silent observer stands in as the engine's required "player". It never
    # acts; every persona is an NPC driven by its agent.
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
