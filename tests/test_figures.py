"""The illustration channel (M1 of the retro-animations design): the engine
cues cards by key on Channel.FIGURE, once per key per game; a close look at a
thing with a ``figure`` property cues its card; adventure events cue theirs;
text renderers stay silent below VERBOSE; and the generated registry
(app/figures.js) can never drift from the reel it is built from."""

import io
import json
import os
import subprocess
import sys

from text_adventure_games.reporting import (
    CaptureRenderer,
    Channel,
    PlainRenderer,
    NORMAL,
    VERBOSE,
)
from text_adventure_games.adventures import tomb_of_nassak_an_rah as tomb

sys.path.insert(0, "app")


def _game():
    g = tomb.build_game(seed=0)
    cap = CaptureRenderer()
    g.parser.set_renderer(cap)
    return g, cap


def test_show_figure_emits_once_per_key():
    g, cap = _game()
    g.show_figure("tesseract")
    g.show_figure("tesseract")
    g.show_figure("epitaph")
    keys = cap.texts(Channel.FIGURE)
    assert keys == ["tesseract", "epitaph"]
    assert g.figures_shown == {"tesseract", "epitaph"}


def test_examine_cues_a_things_card():
    g, cap = _game()
    stone = None
    for c in g.characters.values():
        for it in c.inventory.values():
            if it.name == "glowstone":
                stone = it
    # the merchant's glowstone: move it into the player's hands and look
    if stone is None:  # it lives on the dead merchant, searchable
        merchant = next(
            i for i in g.player.location.items.values() if "merchant" in i.name
        )
        stone = next(it for it in merchant.contents.values() if it.name == "glowstone")
    g.player.add_to_inventory(stone)
    g.do_command("examine glowstone")
    assert cap.texts(Channel.FIGURE) == ["glowstone"]
    g.do_command("examine glowstone")  # once per game, not per look
    assert cap.texts(Channel.FIGURE) == ["glowstone"]


def test_npc_examines_draw_nothing():
    g, cap = _game()
    silas = g.characters["Silas"]
    box = g.items_by_name("manifold box") if hasattr(g, "items_by_name") else None
    # simplest: the hook gates on actor is player -- exercise via show path
    from text_adventure_games.actions.things import Examine

    stone_owner = g.player.location
    # give Silas something with a figure and have HIM examine it
    from text_adventure_games import things

    trinket = things.Item("trinket", "a trinket", "a trinket")
    trinket.set_property("figure", "tesseract")
    silas.add_to_inventory(trinket)
    Examine(g, "examine trinket", actor=silas)()
    assert cap.texts(Channel.FIGURE) == []


def test_stateful_figure_property_is_called_with_the_game():
    g, cap = _game()
    horror = g.characters["fungal horror"]
    fig = horror.get_property("figure")
    assert callable(fig)
    assert fig(g) == "sphere-b"  # coiled in the coffin
    horror.set_property("ablaze", 3)
    assert fig(g) == "autarch-e"  # the bust, burning


def test_seal_event_cues_its_card():
    g, cap = _game()
    canopic = g.locations["Hall of the Canopic Jars"]
    falcon_plinth = canopic.items["falcon plinth"]
    jackal_plinth = canopic.items["jackal plinth"]
    # find the wandering jars wherever the spawns carry them
    jars = {}
    for c in g.characters.values():
        for it in c.inventory.values():
            if it.name in ("falcon jar", "jackal jar"):
                jars[it.name] = it
    falcon_plinth.add_item(jars["falcon jar"])
    jackal_plinth.add_item(jars["jackal jar"])
    g.do_command("wait")  # a turn passes; the placement trigger fires
    assert "seal" in cap.texts(Channel.FIGURE)
    assert "seal" in g.figures_shown


def test_figure_keys_survive_the_journal_replay():
    g, cap = _game()
    g.do_command("search merchant")
    g.do_command("take glowstone")
    g.do_command("examine glowstone")
    assert "glowstone" in g.figures_shown
    g2 = tomb.build_game(seed=0)
    g2.parser.set_renderer(CaptureRenderer())
    g2.replay(list(g.journal))
    assert "glowstone" in g2.figures_shown


def test_text_renderers_stay_silent_below_verbose():
    quiet, loud = io.StringIO(), io.StringIO()
    for level, stream in ((NORMAL, quiet), (VERBOSE, loud)):
        g = tomb.build_game(seed=0)
        g.parser.set_renderer(PlainRenderer(level=level, stream=stream))
        g.show_figure("tesseract")
    assert "tesseract" not in quiet.getvalue()
    assert "[figure: tesseract]" in loud.getvalue()


def test_every_wired_key_exists_in_the_registry():
    """Each figure key the adventure can cue must be a card in figures.js."""
    import gen_figures

    registry = set(gen_figures.generate())
    g, cap = _game()
    wired = set()
    for pool in (g.items_snapshot() if hasattr(g, "items_snapshot") else [],):
        pass  # no global item registry; walk locations + characters instead
    seen = set()

    def _walk(thing):
        if id(thing) in seen:
            return
        seen.add(id(thing))
        fig = thing.properties.get("figure")
        if callable(fig):
            wired.add(fig(g))
        elif fig:
            wired.add(fig)
        for inner in getattr(thing, "contents", {}).values():
            _walk(inner)

    for loc in g.locations.values():
        for it in loc.items.values():
            _walk(it)
        for c in loc.characters.values():
            _walk(c)
            for it in c.inventory.values():
                _walk(it)
    # event-cued keys (not discoverable by walking) + client-cued ones
    wired |= {"seal", "autarch", "autarch-e", "bats", "bats-c", "road", "epitaph"}
    missing = wired - registry
    assert not missing, f"wired keys with no card: {sorted(missing)}"


def test_generated_figures_js_matches_the_reel():
    """The committed figures.js regenerates identically -- no drift."""
    import gen_figures

    committed = open(gen_figures.OUT, encoding="utf-8").read()
    gen_figures.generate()
    fresh = open(gen_figures.OUT, encoding="utf-8").read()
    assert (
        committed == fresh
    ), "app/figures.js is stale -- run python3 app/gen_figures.py"


def test_the_bridge_carries_figure_events():
    import app_api

    app_api.boot(0)
    payload = json.loads(app_api.command("search merchant"))
    app_api.command("take glowstone")
    payload = json.loads(app_api.command("examine glowstone"))
    figs = [e for e in payload["events"] if e["channel"] == "figure"]
    assert [e["text"] for e in figs] == ["glowstone"]
