"""Crafting: combine ingredients into a new item (issue: reusable crafting).

A game declares **recipes** as data -- the way it declares locations and
triggers -- and one generic :class:`~text_adventure_games.actions.things.Craft`
action drives all of them. A recipe consumes a set of ingredients from the
crafter's held items, optionally requires one or more *tools* present but not
consumed (a cooking pot, a forge, a hammer -- station and instrument are the
same thing here), and produces one or more new items.

    game.add_recipe(Recipe(
        name="stew", aliases=["mushroom stew"],
        inputs=[Ingredient("water"), Ingredient("cave mushroom")],
        tools=[Ingredient("pot")],                       # required present, not consumed
        output=lambda g: Item("stew", "a bowl of mushroom stew"),
        result_text="You simmer the mushrooms in spring water into a stew.",
    ))

The player crafts with ``make`` / ``craft`` / ``cook`` / ``combine`` / ... :

    > make stew                 # by output name
    > combine string and stick  # by ingredients
    > cook                       # bare verb: the first recipe satisfiable here

Recipes hold a factory callable, so they are runtime-only (re-registered by
``build_game``, like triggers and behaviors) and not serialized.

INGREDIENT MATCHING. An ``Ingredient`` matches a held item by ``name`` OR by a
``tag`` (any item whose ``tag`` property is truthy -- e.g. ``tag="plank"`` for a
"any 2 planks" recipe). ``count`` consumes that many, summed over the matching
items' ``quantity``: a stackable named item (Item.make_stackable, #134) can
supply ``count > 1`` from a single stack ("2 sticks"), and tag matches sum
across distinct items.

KNOWN RECIPES (#135). By default a recipe is ``known`` (craftable from the
start), so existing games are unchanged. Set ``known=False`` to gate it on
discovery: the Craft action ignores it -- naming it reports "you don't know how
to make that", never the ingredient gap -- until the game calls
``Game.learn_recipe(name)`` (wired to a recipe book, an NPC, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Ingredient:
    """One requirement of a recipe -- matched against a held (or, for tools,
    present) item by name or by a property tag."""

    name: str | None = None
    tag: str | None = None
    count: int = 1

    def matches(self, item) -> bool:
        if self.name is not None and getattr(item, "name", None) == self.name:
            return True
        if self.tag is not None and item.get_property(self.tag):
            return True
        return False

    def label(self) -> str:
        base = self.name or (f"{self.tag}" if self.tag else "something")
        return f"{self.count} {base}" if self.count > 1 else base


def _as_ingredient(spec) -> Ingredient:
    """Coerce a plain string (a name) or an Ingredient into an Ingredient, so
    authors can write ``inputs=["water", "cave mushroom"]``."""
    if isinstance(spec, Ingredient):
        return spec
    return Ingredient(name=str(spec))


@dataclass
class Recipe:
    """A declarative crafting rule. See the module docstring."""

    output: Callable[["object"], object]  # (game) -> Item | list[Item]
    inputs: list = field(default_factory=list)  # consumed, from held items
    tools: list = field(default_factory=list)  # required present, NOT consumed
    name: str | None = None  # craftable name for "make <name>"; default = output's
    aliases: list = field(default_factory=list)
    location: str | None = None  # optional: must be crafted in this room
    result_text: str | None = None
    # Craftable from the start? Default True = always known (existing games
    # unchanged). Set False to gate the recipe on discovery (issue #135); the
    # game then calls Game.learn_recipe(name) from a recipe book, an NPC, etc.
    known: bool = True

    def __post_init__(self):
        self.inputs = [_as_ingredient(i) for i in self.inputs]
        self.tools = [_as_ingredient(t) for t in self.tools]
        # A gated recipe must be referenceable by name/alias, or no
        # learn_recipe() call could ever unlock it (issue #135). Fail fast.
        if not self.known and not self.names():
            raise ValueError(
                "a recipe with known=False needs a name or alias so it can be "
                "learned via Game.learn_recipe()"
            )

    def names(self) -> list[str]:
        """The names this recipe answers to for 'make <name>' lookups."""
        out = [n for n in [self.name, *self.aliases] if n]
        return [n.lower() for n in out]
