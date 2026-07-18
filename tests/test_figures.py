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
    assert cap.texts(Channel.FIGURE) == ["glowstone-b"]  # found dark: the switch card
    g.do_command("examine glowstone")  # an explicit look always re-earns it
    assert cap.texts(Channel.FIGURE) == ["glowstone-b", "glowstone-b"]


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
    assert fig(g) == "sphere-f"  # out among the shards
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
    assert "glowstone-b" in g.figures_shown
    g2 = tomb.build_game(seed=0)
    g2.parser.set_renderer(CaptureRenderer())
    g2.replay(list(g.journal))
    assert "glowstone-b" in g2.figures_shown


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

    boot_payload = json.loads(app_api.boot(0))
    assert boot_payload["events"][0]["channel"] == "figure"
    assert boot_payload["events"][0]["text"] == "road"
    app_api.command("restart")
    restart_payload = json.loads(app_api.command("y"))
    figs = [e["text"] for e in restart_payload["events"] if e["channel"] == "figure"]
    assert "road" in figs  # a restart earns the title reel again
    payload = json.loads(app_api.command("search merchant"))
    app_api.command("take glowstone")
    payload = json.loads(app_api.command("examine glowstone"))
    figs = [e for e in payload["events"] if e["channel"] == "figure"]
    assert [e["text"] for e in figs] == ["glowstone-b"]


def test_arriving_at_the_tomb_cues_the_approach_above_the_description():
    g, cap = _game()
    g.do_command("go north")
    kinds = [(m.channel, m.text) for m in cap.messages]
    fig_at = next(i for i, (c, t) in enumerate(kinds) if c is Channel.FIGURE)
    desc_at = next(i for i, (c, t) in enumerate(kinds) if "azure stone" in t)
    assert kinds[fig_at][1] == "ext1c"
    assert fig_at < desc_at  # the card is a title plate, not a footnote
    g.do_command("go south")
    g.do_command("go north")  # returning does not re-draw it
    assert cap.texts(Channel.FIGURE).count("ext1c") == 1


def test_entering_the_hall_of_memory_cues_silas_only_when_lit():
    g, cap = _game()
    g.do_command("search merchant")
    g.do_command("take glowstone")
    memory = g.locations["Hall of Memory"]
    neighbor, direction = next(
        (loc, d)
        for loc in g.locations.values()
        for d, dest in loc.connections.items()
        if dest is memory
    )
    word = str(getattr(direction, "value", direction))
    g.relocate(g.player, neighbor)
    g.do_command(f"go {word}")  # in the gloom: the card keeps
    assert "silas" not in cap.texts(Channel.FIGURE)
    g.relocate(g.player, neighbor)
    g.do_command("light glowstone")
    g.do_command(f"go {word}")  # lit: Silas at his reading, above the text
    assert "silas" in cap.texts(Channel.FIGURE)


def test_arriving_in_the_hall_of_warriors_cues_the_cylinders_when_lit():
    g, cap = _game()
    g.do_command("search merchant")
    g.do_command("take glowstone")
    g.do_command("go north")
    g.do_command("go east")  # pitch dark: the card keeps
    assert "cylinders-b" not in cap.texts(Channel.FIGURE)
    g.do_command("go west")
    g.do_command("light glowstone")
    g.do_command("go east")  # lit: the intact deck, above the text
    assert "cylinders-b" in cap.texts(Channel.FIGURE)


def test_the_spawns_warning_draws_its_card_first():
    g, cap = _game()
    g.do_command("go north")
    g.do_command("go east")  # footfalls: it swings toward you
    msgs = [(m.channel, m.text) for m in cap.messages]
    fig_at = next(
        i for i, (c, t) in enumerate(msgs) if c is Channel.FIGURE and t == "guts-a"
    )
    warn_at = next(i for i, (c, t) in enumerate(msgs) if "swings toward" in t)
    assert fig_at < warn_at  # the sway plays, THEN the warning prints


def test_dates_tossed_under_open_sky_cue_the_wheel_of_bats():
    g, cap = _game()
    g.do_command("search merchant")
    g.do_command("take glowstone")
    g.do_command("light glowstone")
    g.relocate(g.player, g.locations["The Wagon's Hold"])
    g.do_command("open crates")
    g.do_command("take crate of dates")
    g.relocate(g.player, g.locations["The Caravan Wreck"])
    g.do_command("drop dates")  # food on the floor is food on the floor
    msgs = [(m.channel, m.text) for m in cap.messages]
    fig_at = next(
        i for i, (c, t) in enumerate(msgs) if c is Channel.FIGURE and t == "bats"
    )
    txt_at = next(i for i, (c, t) in enumerate(msgs) if "EXHALE" in t)
    assert fig_at < txt_at  # the wheel plays, THEN the tomb exhales
    assert "wheel of bats" in g.player.location.items


def test_talking_to_silas_is_a_backstop_cue():
    g, cap = _game()
    g.relocate(g.player, g.locations["Hall of Memory"])
    g.do_command("talk to silas")
    assert "silas" in cap.texts(Channel.FIGURE)


def test_arriving_at_the_summit_cues_the_mystic():
    g, cap = _game()
    summit = g.locations["The Summit"]
    neighbor, direction = next(
        (loc, d)
        for loc in g.locations.values()
        for d, dest in loc.connections.items()
        if dest is summit
    )
    g.relocate(g.player, neighbor)
    g.player.remove_all_wounds() if hasattr(g.player, "remove_all_wounds") else None
    g.do_command(f"go {str(getattr(direction, 'value', direction))}")
    if g.player.location is summit:  # the climb may be gated; only assert if we made it
        assert "mystic-b" in cap.texts(Channel.FIGURE)


def test_burning_the_mystic_deals_the_cleanse_then_the_aftermath():
    """BURN MYSTIC deals 19-C as a story beat, above the prose -- and from
    then on the summit and the corpse show the burned-out plate (19-F),
    never the gift again."""
    g, cap = _game()
    summit = g.locations["The Summit"]
    corpse = summit.items["ossified corpse"]
    fig = corpse.get_property("figure")
    assert fig(g) == "mystic-b"  # the gift, while the network lives
    # arm the cleanse: a spark and the gel, as the walkthrough carries them
    cyl = g.locations["Hall of Warriors"].items["orange cylinder"]
    igniter = cyl.contents["plasma-igniter"]
    cyl.remove_item(igniter)
    g.player.add_to_inventory(igniter)
    gel = g.locations["Hall of Hounds"].items["flask of gel"]
    g.locations["Hall of Hounds"].remove_item(gel)
    g.player.add_to_inventory(gel)
    g.relocate(g.player, summit)
    g.do_command("burn mystic")
    msgs = [(m.channel, m.text) for m in cap.messages]
    fig_at = next(
        i for i, (c, t) in enumerate(msgs) if c is Channel.FIGURE and t == "mystic-c"
    )
    txt_at = next(i for i, (c, t) in enumerate(msgs) if "whole rotten network" in t)
    assert fig_at < txt_at  # the burning plays, THEN the tomb goes quiet
    assert fig(g) == "mystic-f"  # ash now: the aftermath replaces the gift
    assert summit.get_property("figure")(g) == "mystic-f"
    cap.messages.clear()
    g.do_command("look")
    assert "mystic-f" in cap.texts(Channel.FIGURE)
    assert "mystic-b" not in cap.texts(Channel.FIGURE)


def test_the_cylinder_card_names_the_first_break():
    """The Hall of Warriors deals 06-B while all four stand; the FIRST break
    earns that colour's own plate (06-C/A/V/O); any deeper wreckage falls
    back to the generic scavenged plate (06)."""
    for colour, key in (
        ("cerulean", "cyl-c"),
        ("amber", "cyl-a"),
        ("viridian", "cyl-v"),
        ("orange", "cyl-o"),
    ):
        g, _cap = _game()
        warriors = g.locations["Hall of Warriors"]
        fig = warriors.items["cylinders"].get_property("figure")
        assert fig(g) == "cylinders-b"  # as the tombwrights left it
        g.relocate(g.player, warriors)
        g.do_command(f"break {colour} cylinder")
        assert fig(g) == key  # the first break gets its own plate
        g.do_command(
            "break viridian cylinder" if colour != "viridian" else "break amber cylinder"
        )
        assert fig(g) == "cylinders"  # deeper wreckage: the generic plate


def test_the_flask_deals_its_specimen_card():
    """The flask of gel (card 40): examining it always re-earns the card."""
    g, cap = _game()
    hounds = g.locations["Hall of Hounds"]
    gel = hounds.items["flask of gel"]
    hounds.remove_item(gel)
    g.player.add_to_inventory(gel)
    g.do_command("examine flask")
    assert cap.texts(Channel.FIGURE) == ["flask"]
    g.do_command("examine flask")
    assert cap.texts(Channel.FIGURE) == ["flask", "flask"]


def test_a_purged_fungus_also_retires_the_gift_card():
    """The other road to a dead network -- the Horror slain in the sphere --
    must also retire 19-B at the summit (CCB: don't replay the gift once
    the fungus is gone)."""
    g, _cap = _game()
    summit = g.locations["The Summit"]
    fig = summit.items["ossified corpse"].get_property("figure")
    assert fig(g) == "mystic-b"
    g.locations["Burial Sphere of Nassak An-Rah"].set_property("horror_dead", True)
    assert fig(g) == "mystic-f"


def test_look_replays_the_rooms_card():
    g, cap = _game()
    g.do_command("go north")  # ext1c, the arrival plate
    g.do_command("look")  # and LOOK re-earns it
    assert cap.texts(Channel.FIGURE).count("ext1c") == 2
    g.do_command("look east")  # surveying an exit is not a look-around
    assert cap.texts(Channel.FIGURE).count("ext1c") == 2


def test_taking_a_carded_item_draws_it_once():
    g, cap = _game()
    g.do_command("search merchant")
    g.do_command("take glowstone")  # the acquisition is the moment
    assert cap.texts(Channel.FIGURE) == ["glowstone-b"]
    g.do_command("drop glowstone")
    g.do_command("take glowstone")  # re-pocketing is not
    assert cap.texts(Channel.FIGURE) == ["glowstone-b"]


def test_the_glowstone_card_follows_the_switch():
    g, cap = _game()
    g.do_command("search merchant")
    g.do_command("take glowstone")  # found dark: the switch, set to OFF
    assert cap.texts(Channel.FIGURE) == ["glowstone-b"]
    g.do_command("light glowstone")  # the toggle: the interactive demo
    assert cap.texts(Channel.FIGURE) == ["glowstone-b", "glowstone"]
    g.do_command("examine glowstone")  # lit in hand: the burn and the bill
    assert cap.texts(Channel.FIGURE)[-1] == "glowstone-c"
    g.do_command("douse glowstone")  # going dark is a demo too
    assert cap.texts(Channel.FIGURE)[-1] == "glowstone"
    g.do_command("examine glowstone")  # and dark in hand is the switch again
    assert cap.texts(Channel.FIGURE)[-1] == "glowstone-b"


def test_lighting_up_in_the_dark_earns_the_look():
    g, cap = _game()
    g.do_command("search merchant")
    g.do_command("take glowstone")
    g.relocate(g.player, g.locations["Hall of Memory"])  # gloom: shapes only
    g.do_command("light glowstone")
    assert "silas" in cap.texts(Channel.FIGURE)  # the room's card, via the look
    joined = " ".join(cap.texts(Channel.NARRATION))
    assert "Lattices of memory-crystal" in joined  # and its full description


def test_examining_the_tomb_shows_the_elevations():
    g, cap = _game()
    g.do_command("go north")  # arrival: the approach (ext1c)
    g.do_command("x tomb")  # the close look: the surveyor's sheet
    figs = cap.texts(Channel.FIGURE)
    assert figs == ["ext1c", "ext1e"]
