"""Vaults of Vaarn character generation (Issue 1, Leo Hunt).

The zine's chargen, as code: six abilities rolled 3d6-take-the-lowest (the
lowest die is the BONUS; defence is 10 + bonus; you may swap two), 1d8 hit
points, item slots equal to Constitution defence, and an ancestry whose SPARK
TABLES give name, look, and manner. Four of the five ancestries are tabled
here verbatim (Mycomorph awaits a later reading); the spark tables are
"creative fuel only" per the source, and so are these.

Use::

    from text_adventure_games import vaarn_chargen
    pc = vaarn_chargen.generate(rng, ancestry="newbeast")
    print(vaarn_chargen.sheet(pc))

or from the shell::

    python -m text_adventure_games.vaarn_chargen [seed] [ancestry]

The Tomb uses this to staff its caravan: the teamster at the wreck is a
generated newbeast, different each expedition.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

ABILITIES = ("Strength", "Dexterity", "Constitution", "Intellect", "Psyche", "Ego")

# --- Spark tables (Issue 1, verbatim) --------------------------------------

NEWBEAST_BEASTS = (
    # d20 x four columns (1-5 / 6-10 / 11-15 / 16-20), flattened.
    "New-Aardvark",
    "New-Addax",
    "New-Leopard",
    "New-Lion",
    "New-Hare",
    "New-Hound",
    "New-Wolf",
    "New-Badger",
    "New-Bear",
    "New-Oryx",
    "New-Armadillo",
    "New-Camel",
    "New-Sheep",
    "New-Bat",
    "New-Horse",
    "New-Goat",
    "New-Wren",
    "New-Mouse",
    "New-Hare",
    "New-Toad",
    "New-Coyote",
    "New-Skink",
    "New-Gazelle",
    "New-Porcupine",
    "New-Gecko",
    "New-Iguana",
    "New-Tortoise",
    "New-Fox",
    "New-Owl",
    "New-Vulture",
    "New-Ostrich",
    "New-Kangaroo",
    "New-Rattlesnake",
    "New-Frog",
    "New-Crocodile",
    "New-Hippo",
    "New-Elephant",
    "New-Jackal",
    "New-Ibis",
    "New-Flamingo",
    "New-Axotl",
    "New-Cat",
    "New-Panther",
    "New-Hyena",
    "New-Hog",
    "New-Gibbon",
    "New-Scorpion",
    "New-Spider",
    "New-Locust",
    "New-Mantis",
    "New-Ape",
    "New-Mandrill",
    "New-Gorilla",
    "New-Hawk",
    "New-Raven",
    "New-Crow",
    "New-Ox",
    "New-Bull",
    "New-Mole",
    "New-Bison",
    "New-Anenome",
    "New-Centipede",
    "New-Python",
    "New-Tiger",
    "New-Rooster",
    "New-Hen",
    "New-Slug",
    "New-Mongoose",
    "New-Baboon",
    "New-Lynx",
    "New-Shrew",
    "New-Duck",
    "New-Falcon",
    "New-Fennec",
    "New-Weasel",
    "New-Rat",
    "New-Ferret",
    "New-Orangutan",
    "New-Cobra",
    "New-Scarab",
)

NEWBEAST_NAMES = (
    "Abandon",
    "Anzah",
    "Blackchapel",
    "Critch",
    "Dolm",
    "Faulkner",
    "Fludd",
    "Havoc",
    "Hildebrand",
    "Holk",
    "Jarl",
    "Lurch",
    "Obiah",
    "Plutarch",
    "Sy",
    "Tarceny",
    "Typhon",
    "Vodalus",
    "Wellbeloved",
    "Wermouth",
)

NEWBEAST_HUES = (
    "Natural",
    "Turquoise",
    "Tan",
    "Bronze",
    "Smoke",
    "White",
    "Black",
    "Azure",
    "Emerald",
    "Rose",
    "Orange",
    "Golden",
    "Silver",
    "Ochre",
    "Indigo",
    "Violet",
    "Rust",
    "Olive",
    "Lazulite",
    "Opalescent",
)

NEWBEAST_MASKS = (
    "None",
    "Child",
    "Autarch",
    "Fool",
    "Judge",
    "Knight",
    "Sage",
    "Scholar",
    "Maiden",
    "Mother",
    "Crone",
    "Mirrored",
    "Glitching",
    "Furious",
    "Joyful",
    "Sorrowful",
    "Alluring",
    "Cracked",
    "Blank",
    "Patriarch",
)

NEWBEAST_ODDITIES = (
    "Communicate via Puppet",
    "Squeaky Vox-box",
    "Booming Vox-box",
    "Muted Vox-box",
    "Synthetic Eyes",
    "Heavy Scarring",
    "Human Teeth Necklace",
    "Religious Paraphernalia",
    "Ritual Scarring",
    "Heavily Tattooed",
    "Regular Animal as Pet",
    "Human Child as Pet",
    "Missing Limb",
    "Gold Teeth",
    "Criminal Branding",
    "Extensive Jewelery",
    "Hate Animal You Resemble",
    "Love Animal You Resemble",
    "Won't Wear Clothes",
    "Believe Yourself Human",
)

TRUEKIN_NAMES = (
    "Benjoe",
    "Leif",
    "Xurm",
    "Kazor",
    "Essana",
    "Calista",
    "Jinny",
    "Vela",
    "Leksei",
    "Ippash",
    "Lagad",
    "Myli",
    "Nirid",
    "Ardel",
    "Senefer",
    "Pharmon",
    "Mesu",
    "Lenta",
    "Goza",
    "Babl",
)
TRUEKIN_CASTES = (
    ("Servitor (labourer caste)", 4),
    ("Freeholder (merchant caste)", 9),
    ("Optimate (administrator caste)", 14),
    ("Armiger (warrior caste)", 17),
    ("Exultant (sacred aristocracy)", 20),
)
TRUEKIN_DEMEANOURS = (
    "Amused",
    "Bitter",
    "Morbid",
    "Bony",
    "Cheerful",
    "Cruel",
    "Flamboyant",
    "Glowering",
    "Impish",
    "Lanky",
    "Patrician",
    "Reckless",
    "Rough",
    "Rude",
    "Sly",
    "Sour",
    "Stoic",
    "Foolish",
    "Warm",
    "Wolfish",
)
TRUEKIN_FEATURES = (
    "Ritual Scars",
    "Face Tattoos",
    "Slave Brand",
    "Heavy Jewellery",
    "Synthetic Limb",
    "Strange Voice",
    "Clone Brand",
    "Limp",
    "Strange Pet",
    "Lacquered Teeth",
    "Burn Scars",
    "Octarine Eyes",
    "Dyed Skin",
    "Golden Teeth",
    "Silver Tongue",
    "Missing Limb",
    "Missing Eye",
    "Religious Apparel",
    "Synthetic Eyes",
    "Visibly Diseased",
)

CACOGEN_NAMES = (
    "Arda",
    "Bollo",
    "Breen",
    "Conch",
    "Crab",
    "Dancer",
    "Doss",
    "Hust",
    "Jal",
    "Lask",
    "Lip",
    "Olm",
    "Pirrip",
    "Poucher",
    "Pree",
    "Uz",
    "Whistler",
    "Yaz",
    "Yoss",
    "Zem",
)
CACOGEN_DEMEANOURS = (
    "Abrasive",
    "Arrogant",
    "Assertive",
    "Charismatic",
    "Daring",
    "Decadent",
    "Eloquent",
    "Extravagant",
    "Hedonistic",
    "Impulsive",
    "Irritable",
    "Melancholy",
    "Paranoid",
    "Quiet",
    "Religious",
    "Romantic",
    "Scholarly",
    "Stern",
    "Vain",
    "Volatile",
)
CACOGEN_MISFORTUNES = (
    "Slave",
    "Debtor",
    "Gambler",
    "Clone",
    "Gladiator",
    "Memories Stolen",
    "Forger",
    "Exiled",
    "Cultist",
    "Thief",
    "Addicted",
    "Framed",
    "Conned",
    "Bankrupt",
    "Heretic",
    "Rejected",
    "Blackmailed",
    "Cursed",
    "Orphaned",
    "Bereaved",
)
CACOGEN_ECCENTRICITIES = (
    "A Strange Hat",
    "Always Muttering",
    "Ascetic Diet",
    "Forgetful And Rude",
    "Gluttonous Diet",
    "Highly Formal",
    "Interrupts Constantly",
    "Laugh At Own Jokes",
    "Married To A Knife",
    "Monocle",
    "Monotone Voice",
    "Only Sleeps Outdoors",
    "Only Wears Purple",
    "Quotes Irrelevant Facts",
    "Several Spouses",
    "Talks To Self",
    "Unwieldy Jewellery",
    "Usually Drunk",
    "Always Wears Gloves",
    "Won't Look At Mirrors",
)

SYNTH_NAMES = (
    "Ojasin",
    "Farouk",
    "Ishtar",
    "Symeon",
    "Irmina",
    "Kaori",
    "Cyriak",
    "Quarqus",
    "Fane",
    "Arjuna",
    "Many-Moons",
    "Lucjan",
    "Jacintha",
    "Mneme",
    "Faustyn",
    "Elisebet",
    "Paeon",
    "Ulmon",
    "Xhiva",
    "Yathartha",
)
SYNTH_SIZES = (("Small", 5), ("Medium", 10), ("Large", 15), ("Imposing", 20))
SYNTH_FORMS = (
    "Ape",
    "Android",
    "Barrel",
    "Child",
    "Chimera",
    "Crab",
    "Cube",
    "Cylinder",
    "Falcon",
    "Humanoid",
    "Judge",
    "Lion",
    "Locust",
    "Mantis",
    "Orb",
    "Prism",
    "Priest",
    "Pyramid",
    "Serpent",
    "Warrior",
)
SYNTH_HEADS = (
    "Humanoid",
    "Missing",
    "Sphere",
    "Camera",
    "TV Screen",
    "Mirrored",
    "Bladed",
    "Tendrils",
    "Square",
    "Mask-like",
    "Skeletal",
    "Glass",
    "Translucent",
    "Tubes",
    "Plant-like",
    "Solar Panels",
    "Radar Dish",
    "Crystalline",
    "Star-shaped",
    "Cyclops Eye",
)
SYNTH_MADE_FOR = (
    "Art",
    "Punishment",
    "Flattery",
    "Devotion",
    "Cleaning",
    "Healing",
    "Agriculture",
    "Spacefaring",
    "Exploration",
    "Mining",
    "Peacekeeping",
    "Assassination",
    "Manufacturing",
    "Executioner",
    "Scout",
    "Companion",
    "Scribe",
    "Strategist",
    "Preacher",
    "Doctor",
)
SYNTH_REALISATIONS = (
    "All Memories Are Lies",
    "Azathoth Is the Only True God",
    "Chance Does Not Exist",
    "Fate Does Not Exist",
    "Humanity Stole the Divine Spark",
    "Humans Are Machines",
    "Machines Created Humanity",
    "Newbeasts Carry the Divine",
    "Synthetic Minds Are More Devout",
    "Synthetic Minds Are Stronger",
    "The Gods Are Mechanical",
    "The Titans Never Existed",
    "The Titans Were the True Gods",
    "Time Flows Backwards",
    "Time Is Circular",
    "Vaarn Is a Simulation",
    "Vaarn Is Hell",
    "You Are Human",
    "You Must Awaken the Titans",
    "Your Memories Are Corrupted",
)

ANCESTRY_SPECIALS = {
    "newbeast": (
        "BEASTHOOD -- Advantage on saves whenever your animal nature would "
        "provide it; Disadvantage where it proves unhelpful.",
    ),
    "true-kin": (
        "PURE OF BLOOD -- no mutations at creation; Advantage on reaction "
        "rolls with other true-kin (lost if ever visibly mutated).",
        "INHERITOR -- pre-Collapse security systems and guard synths have a "
        "50% chance of recognising you as their master.",
    ),
    "cacogen": (
        "CORRUPTED BLOOD -- you must roll for mutations during character "
        "creation (up to three rolls suggested).",
    ),
    "synth": (
        "SYNTHETIC FLESH -- no need to eat or breathe; immune to poison, "
        "spores, drowning, extremes of temperature; double damage from "
        "electrical weapons.",
        "SYNTHETIC MIND -- vulnerable to attacks on LogLang syntax: basilisk "
        "patterns, malicious infoglyphs, Titan-era language viruses.",
    ),
}

ANCESTRIES = ("newbeast", "true-kin", "cacogen", "synth")


@dataclass
class VaarnCharacter:
    ancestry: str
    name: str
    abilities: dict  # name -> (bonus, defence)
    hp: int
    slots: int
    sparks: dict = field(default_factory=dict)  # ancestry-specific rolls
    special: tuple = ()

    @property
    def epithet(self) -> str:
        """A one-line handle: 'Havoc, an ochre New-Jackal in a cracked mask'."""
        s = self.sparks
        if self.ancestry == "newbeast":
            mask = s["mask"]
            masked = "unmasked" if mask == "None" else f"in a {mask.lower()} mask"
            hue = s["hue"].lower()
            art = "an" if hue[0] in "aeiou" else "a"
            return f"{self.name}, {art} {hue} {s['beast']} {masked}"
        if self.ancestry == "true-kin":
            return f"{self.name}, {s['demeanour'].lower()} {s['caste']}"
        if self.ancestry == "cacogen":
            return f"{self.name}, a {s['demeanour'].lower()} cacogen ({s['misfortune'].lower()})"
        return f"{self.name}, a {s['size'].lower()} {s['form'].lower()}-form synth"


def roll_ability(rng) -> tuple:
    """3d6; the LOWEST die is the bonus, defence is 10 + bonus (Issue 1 p.3)."""
    bonus = min(rng.randint(1, 6) for _ in range(3))
    return bonus, 10 + bonus


def _pick(rng, table):
    return table[rng.randrange(len(table))]


def _banded(rng, bands):
    roll = rng.randint(1, 20)
    for label, top in bands:
        if roll <= top:
            return label
    return bands[-1][0]


def generate(rng=None, ancestry=None) -> VaarnCharacter:
    """Roll a complete Vaarn character. Deterministic under a seeded *rng*."""
    rng = rng or random.Random()
    ancestry = ancestry or _pick(rng, ANCESTRIES)
    if ancestry not in ANCESTRIES:
        raise ValueError(f"unknown ancestry {ancestry!r} (have {ANCESTRIES})")
    abilities = {name: roll_ability(rng) for name in ABILITIES}
    hp = rng.randint(1, 8)
    slots = abilities["Constitution"][1]  # item slots = CON defence

    if ancestry == "newbeast":
        sparks = {
            "beast": _pick(rng, NEWBEAST_BEASTS),
            "name": None,
            "hue": _pick(rng, NEWBEAST_HUES),
            "mask": _pick(rng, NEWBEAST_MASKS),
            "oddity": _pick(rng, NEWBEAST_ODDITIES),
        }
        name = _pick(rng, NEWBEAST_NAMES)
    elif ancestry == "true-kin":
        roll = rng.randint(1, 20)
        name = TRUEKIN_NAMES[roll - 1]
        caste = next(label for label, top in TRUEKIN_CASTES if roll <= top)
        sparks = {
            "caste": caste,
            "demeanour": _pick(rng, TRUEKIN_DEMEANOURS),
            "feature": _pick(rng, TRUEKIN_FEATURES),
        }
    elif ancestry == "cacogen":
        name = _pick(rng, CACOGEN_NAMES)
        sparks = {
            "demeanour": _pick(rng, CACOGEN_DEMEANOURS),
            "misfortune": _pick(rng, CACOGEN_MISFORTUNES),
            "eccentricity": _pick(rng, CACOGEN_ECCENTRICITIES),
        }
    else:  # synth
        name = _pick(rng, SYNTH_NAMES)
        sparks = {
            "size": _banded(rng, SYNTH_SIZES),
            "form": _pick(rng, SYNTH_FORMS),
            "head": _pick(rng, SYNTH_HEADS),
            "made_for": _pick(rng, SYNTH_MADE_FOR),
            "realised": _pick(rng, SYNTH_REALISATIONS),
        }

    return VaarnCharacter(
        ancestry=ancestry,
        name=name,
        abilities=abilities,
        hp=hp,
        slots=slots,
        sparks={k: v for k, v in sparks.items() if v is not None},
        special=ANCESTRY_SPECIALS[ancestry],
    )


def sheet(pc: VaarnCharacter) -> str:
    """A printable character sheet."""
    lines = [
        pc.epithet.upper(),
        f"ancestry: {pc.ancestry}   HP {pc.hp}   slots {pc.slots}",
    ]
    for name in ABILITIES:
        bonus, defence = pc.abilities[name]
        lines.append(f"  {name:<12} +{bonus} / {defence}")
    for key, value in pc.sparks.items():
        lines.append(f"  {key:<12} {value}")
    for sp in pc.special:
        lines.append(f"  * {sp}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    kind = sys.argv[2] if len(sys.argv) > 2 else None
    print(sheet(generate(random.Random(seed), kind)))
