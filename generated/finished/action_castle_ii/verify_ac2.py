"""Manual verification harness for Action Castle II.

Plays the champion walkthrough and exercises every reported bug. Run with:
    uv run python generated/original/action_castle_ii/verify_ac2.py
"""

import importlib.util
from pathlib import Path

from text_adventure_games.reporting import CaptureRenderer, Channel

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("ac2", HERE / "action_castle_ii.py")
ac2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac2)

PASS, FAIL = "PASS", "FAIL"
results = []


def fresh():
    game = ac2.build_game()
    cap = CaptureRenderer()
    game.parser.set_renderer(cap)
    return game, cap


def run(game, cap, cmd):
    cap.drain()
    # Go through Game.do_command so the turn loop fires (NPC behaviors, etc.).
    # parse_command alone skips end_turn, which means Rosemary's follow never
    # gets a chance to run between player commands.
    game.do_command(cmd)
    out = {
        "narration": " ".join(
            cap.texts(Channel.NARRATION) + cap.texts(Channel.NPC_NARRATION)
        ),
        "blocked": " ".join(cap.texts(Channel.BLOCKED)),
    }
    return out


def teleport(game, loc_name):
    dest = game.locations[loc_name]
    cur = game.player.location
    if cur is not None and game.player.name in cur.characters:
        cur.remove_character(game.player)
    dest.add_character(game.player)


def check(label, cond, detail=""):
    results.append((PASS if cond else FAIL, label, detail))


# --------------------------------------------------------------------------
# 1. Champion walkthrough wins (now starting with "drop penny in well")
# --------------------------------------------------------------------------
WALK = [
    "get slippers",
    "out",
    "drop penny in well",
    "east",
    "south",
    "board boat",
    "get blanket",
    "north",
    "west",
    "west",
    "give blanket to rosemary",
    "east",
    "east",
    "north",
    "get axe",
    "south",
    "west",
    "south",
    "give axe to smith",
    "north",
    "east",
    "south",
    "south",
    "give slippers to hermit",
    "north",
    "north",
    "north",
    "east",
    "enter moat",
    "move stone",
    "enter tunnel",
    "south",
    "wake dragon",
    "choose wits",
    "say yes",
    "answer a wise man",
    "choose sword",
    "north",
    "east",
    "up",
    "up",
    "up",
    "give sword to king",
    "accept",
]
game, cap = fresh()
failed_step = None
for cmd in WALK:
    out = run(game, cap, cmd)
    if out["blocked"] and not game.is_game_over():
        failed_step = (cmd, out["blocked"])
        break
check(
    "champion walkthrough wins",
    game.is_won() and failed_step is None,
    f"failed at {failed_step}" if failed_step else "",
)

# --------------------------------------------------------------------------
# 2. drop penny in well (alias) consumes the penny
# --------------------------------------------------------------------------
game, cap = fresh()
run(game, cap, "out")
out = run(game, cap, "drop penny in well")
check(
    "drop penny in well -> well flavor", "plink" in out["narration"], out["narration"]
)
check("penny consumed", "penny" not in game.player.inventory)

# --------------------------------------------------------------------------
# 3. look <dir> describes the exit and does NOT move the player
# --------------------------------------------------------------------------
game, cap = fresh()
run(game, cap, "out")  # Town Square
run(
    game, cap, "east"
)  # Old Pond Road (north->Bend, south->Old Pond, west->Town Square)
before = game.player.location.name
out = run(game, cap, "look north")
check(
    "look north describes exit",
    "Bend in the Road" in out["narration"],
    out["narration"],
)
check(
    "look north does not move",
    game.player.location.name == before,
    game.player.location.name,
)
out = run(game, cap, "look south")
check("look south describes exit", "Old Pond" in out["narration"], out["narration"])

# --------------------------------------------------------------------------
# 4. ask rosemary to follow -> correct flavor (not the greeting)
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Town Hall")
out = run(game, cap, "ask rosemary to follow")
check(
    "ask rosemary to follow -> chilly line",
    "chilly" in out["narration"],
    out["narration"],
)
check(
    "ask rosemary to follow != greeting",
    "blushes" not in out["narration"],
    out["narration"],
)

# --------------------------------------------------------------------------
# 5. propose at the wrong place -> gentle redirect, not [blocked]
# --------------------------------------------------------------------------
game, cap = fresh()
out = run(game, cap, "propose")
check(
    "propose elsewhere -> redirect text",
    "romantic location" in out["narration"],
    out["narration"],
)
check("propose elsewhere not blocked", not out["blocked"], out["blocked"])

# --------------------------------------------------------------------------
# 6. give blanket -> Rosemary follows; row boat -> Middle of Pond; propose
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Town Hall")
# bring a blanket
blanket = game.locations["Old Pond"].items.get("blanket")
game.player.add_to_inventory(blanket)
run(game, cap, "give blanket to rosemary")
check(
    "blanket sets is_following",
    game.characters["rosemary"].get_property("is_following"),
)
# Walk to the pond. With adjacency-based follow, Rosemary catches up one
# room per player command -- the only way she gets there is on foot.
run(game, cap, "east")  # Town Hall -> Town Square
run(game, cap, "east")  # Town Square -> Old Pond Road
run(game, cap, "south")  # Old Pond Road -> Old Pond
check(
    "rosemary walked to Old Pond",
    game.characters["rosemary"].location.name == "Old Pond",
    game.characters["rosemary"].location.name,
)
out = run(game, cap, "row boat")
check(
    "row boat -> Middle of the Pond",
    game.player.location.name == "Middle of the Pond",
    game.player.location.name,
)
check(
    "rosemary follows to the pond via row boat",
    game.characters["rosemary"].location.name == "Middle of the Pond",
    game.characters["rosemary"].location.name,
)
out = run(game, cap, "propose")
check(
    "propose without ring narrates empty pockets",
    "pockets are empty" in out["narration"].lower()
    or "without a ring" in out["narration"].lower(),
    out["narration"],
)
check(
    "propose without ring does NOT betroth",
    not game.player.get_property("is_betrothed"),
)
check("propose without ring does NOT end the game", not game.is_game_over())

# --------------------------------------------------------------------------
# 6b. Ask Rosemary to follow speaks the right line in each state
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Town Hall")
out = run(game, cap, "ask rosemary to follow")
check(
    "ask-to-follow (pre-blanket) says 'chilly'",
    "chilly" in out["narration"],
    out["narration"],
)
blanket = game.locations["Old Pond"].items.get("blanket")
game.player.add_to_inventory(blanket)
run(game, cap, "give blanket to rosemary")
out = run(game, cap, "ask rosemary to follow")
check(
    "ask-to-follow (post-blanket) acknowledges following",
    "already" in out["narration"].lower() or "side" in out["narration"].lower(),
    out["narration"],
)

# --------------------------------------------------------------------------
# 6c. Follow walks the map: blocklist + reunion + no teleport past Bend
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Town Hall")
blanket = game.locations["Old Pond"].items.get("blanket")
game.player.add_to_inventory(blanket)
run(game, cap, "give blanket to rosemary")
# Walk together to Old Pond (3 steps).
run(game, cap, "east")
run(game, cap, "east")
run(game, cap, "south")
check(
    "rosemary walked to Old Pond",
    game.characters["rosemary"].location.name == "Old Pond",
    game.characters["rosemary"].location.name,
)
# Player ventures to a blocklisted room -- she refuses.
run(game, cap, "south")  # Old Pond -> Hermit's Cave
check(
    "rosemary does NOT follow to Hermit's Cave",
    game.characters["rosemary"].location.name == "Old Pond",
    game.characters["rosemary"].location.name,
)
# Player comes back -- she's still waiting at the pond.
run(game, cap, "north")
check(
    "rosemary is right where the player left her",
    game.characters["rosemary"].location.name == "Old Pond",
    game.characters["rosemary"].location.name,
)
# Player walks north -- she steps to keep up.
run(game, cap, "north")  # Old Pond -> Old Pond Road
check(
    "rosemary resumes following north",
    game.characters["rosemary"].location.name == "Old Pond Road",
    game.characters["rosemary"].location.name,
)
run(game, cap, "north")  # Old Pond Road -> Bend in the Road
check(
    "rosemary follows to Bend in the Road",
    game.characters["rosemary"].location.name == "Bend in the Road",
    game.characters["rosemary"].location.name,
)
# At the Bend the player can press east into Action Castle -- she stays.
run(game, cap, "east")  # Bend -> Action Castle (blocklisted)
check(
    "rosemary does NOT follow into Action Castle",
    game.characters["rosemary"].location.name == "Bend in the Road",
    game.characters["rosemary"].location.name,
)
# Even if the player presses on past the moat, she never teleports past
# the Bend -- there's no walkable path from where she stands to Underground.
# (This is the bug that the old teleport-based follow let slip.)
axe = game.locations["Bend in the Road"].items.get("axe")
if axe is not None and axe.location is not None:
    # The walkthrough leaves the axe at the smithy after sharpening; if it's
    # still here, give it to the player so they can survive the moat.
    axe.set_property("is_sharp", True)
    axe.location.remove_item(axe)
    game.player.add_to_inventory(axe)
else:
    sharp_axe = ac2.things.Item("axe", "a sharp axe", "Sharp.")
    sharp_axe.set_property("is_sharp", True)
    game.player.add_to_inventory(sharp_axe)
run(game, cap, "enter moat")  # Bend... wait, player is at Action Castle now.
check(
    "player crossed into Moat (sharp axe)",
    game.player.location.name == "Moat",
    game.player.location.name,
)
# Reveal the tunnel and dive deeper so Rosemary would have to teleport
# across the moat to keep up -- she doesn't.
game.locations["Moat"].items["walls"].set_property("tunnel_revealed", True)
run(game, cap, "enter tunnel")
check(
    "player at Underground",
    game.player.location.name == "Underground",
    game.player.location.name,
)
check(
    "rosemary did NOT teleport past the Bend",
    game.characters["rosemary"].location.name == "Bend in the Road",
    game.characters["rosemary"].location.name,
)

# --------------------------------------------------------------------------
# 6d. Marriage ending: propose at the pond WITH the ring -> game over.
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Town Hall")
blanket = game.locations["Old Pond"].items.get("blanket")
game.player.add_to_inventory(blanket)
run(game, cap, "give blanket to rosemary")
# Slip the dragon's ring into the player's pocket (the only way to get it is
# via Choose_Ring, which also teleports them; we shortcut here).
ring = game.locations["Treasure Trove"].items.get("ring")
ring.location.remove_item(ring)
game.player.add_to_inventory(ring)
# Walk Rosemary out to the pond.
run(game, cap, "east")
run(game, cap, "east")
run(game, cap, "south")
run(game, cap, "row boat")
out = run(game, cap, "propose")
check(
    "marriage ending narrates the ring",
    "ring" in out["narration"].lower() and "happily" in out["narration"].lower(),
    out["narration"],
)
check("marriage ending ends the game", game.is_game_over())
check("marriage ending counts as a win", game.is_won())

# --------------------------------------------------------------------------
# 7. examine location + features
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Action Castle")
out = run(game, cap, "examine moat")
check("examine moat works", "moat" in out["narration"].lower(), out["narration"])
teleport(game, "Bend in the Road")
out = run(game, cap, "examine stump")
check("examine stump works", "stump" in out["narration"].lower(), out["narration"])
teleport(game, "Moat")
out = run(game, cap, "examine tunnel")
check("examine tunnel works", "tunnel" in out["narration"].lower(), out["narration"])
teleport(game, "Treasure Trove")
out = run(game, cap, "examine gold")
check("examine gold works", "gold" in out["narration"].lower(), out["narration"])

# --------------------------------------------------------------------------
# 8. give axe to smith sharpens AND returns it
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Smithy")
axe = game.locations["Bend in the Road"].items.get("axe")
game.player.add_to_inventory(axe)
run(game, cap, "give axe to smith")
check("axe is sharpened", axe.get_property("is_sharp"))
check("axe returned to player", "axe" in game.player.inventory)
check(
    "axe description updates to 'sharpened'",
    "sharpened" in axe.description.lower() and "dulled" not in axe.description.lower(),
    axe.description,
)
check(
    "axe examine_text updates after sharpening",
    "dulled" not in axe.examine_text.lower(),
    axe.examine_text,
)
# A second sharpening should be a no-op (precondition catches it).
out = run(game, cap, "give axe to smith")
check(
    "second sharpening rejected gracefully",
    "already" in (out["blocked"] + out["narration"]).lower(),
    out,
)

# --------------------------------------------------------------------------
# 8b. talk to hermit about prophecy returns the prophecy line
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Hermit's Cave")
out = run(game, cap, "talk to hermit about prophecy")
check(
    "talk-prophecy returns prophecy line",
    "champion will arise" in out["narration"].lower(),
    out["narration"],
)
# The bare 'talk to hermit' still falls back to the mumble line.
out = run(game, cap, "talk to hermit")
check(
    "bare talk to hermit still mumbles",
    "mumbles" in out["narration"].lower(),
    out["narration"],
)
# Out-of-room ask fails with a real reason, not 'Nothing happens'.
teleport(game, "Old Pond")
out = run(game, cap, "ask hermit about prophecy")
check(
    "ask hermit elsewhere fails informatively",
    "hermit isn't here" in (out["blocked"] + out["narration"]).lower(),
    out,
)

# --------------------------------------------------------------------------
# 8c. choose ring is survivable: ring to inventory, teleport, hermit gone
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Treasure Trove")
# Dragon must be defeated before any "choose ..." action is allowed.
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
run(game, cap, "say yes")
run(game, cap, "answer a wise man")
out = run(game, cap, "choose ring")
check(
    "choose ring does NOT end the game",
    not game.is_game_over(),
    str(game.is_game_over()),
)
check(
    "choose ring narrates the chute",
    "tumble" in out["narration"].lower(),
    out["narration"],
)
check("ring is in player inventory", "ring" in game.player.inventory)
check(
    "player teleported to Hermit's Cave",
    game.player.location.name == "Hermit's Cave",
    game.player.location.name,
)
check(
    "hermit is gone from the scene",
    game.characters["hermit"].location is None
    or "hermit" not in game.locations["Hermit's Cave"].characters,
    str(game.characters["hermit"].location),
)

# --------------------------------------------------------------------------
# 9. catfish kills you if you enter the moat without a sharp blade
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Action Castle")
out = run(game, cap, "enter moat")
check("unarmed moat entry is lethal", game.is_game_over(), str(game.is_game_over()))
check("catfish death narrated", "catfish" in out["narration"].lower(), out["narration"])
check(
    "did not reach the Moat",
    game.player.location.name == "Action Castle",
    game.player.location.name,
)

# 9b. with a sharp axe you survive
game, cap = fresh()
teleport(game, "Action Castle")
axe = game.locations["Bend in the Road"].items.get("axe")
axe.set_property("is_sharp", True)
game.player.add_to_inventory(axe)
run(game, cap, "enter moat")
check(
    "armed moat entry survives",
    game.player.location.name == "Moat" and not game.is_game_over(),
    game.player.location.name,
)

# --------------------------------------------------------------------------
# 10. move stone is required before entering the tunnel
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Moat")
out = run(game, cap, "enter tunnel")
check(
    "tunnel blocked before move stone",
    game.player.location.name == "Moat" and bool(out["blocked"]),
    out["blocked"],
)
run(game, cap, "move stone")
run(game, cap, "enter tunnel")
check(
    "tunnel open after move stone",
    game.player.location.name == "Underground",
    game.player.location.name,
)

# --------------------------------------------------------------------------
# 11. choose wits asks first; say yes poses the riddle; say no backs out
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Treasure Trove")
dragon = game.locations["Treasure Trove"].items["dragon"]
run(game, cap, "wake dragon")
out = run(game, cap, "choose wits")
check(
    "choose wits asks 'are you ready'",
    "are you ready" in out["narration"].lower(),
    out["narration"],
)
check(
    "choose wits does NOT immediately pose the riddle",
    not dragon.get_property("is_riddle_posed"),
)
check(
    "choose wits marks dragon awaiting yes/no",
    dragon.get_property("awaiting_yes_no"),
)
# Trying to answer before saying yes should be rejected by the riddle gate.
out = run(game, cap, "answer a wise man")
check(
    "answer rejected before saying yes",
    bool(out["blocked"]),
    out,
)
out = run(game, cap, "say yes")
check(
    "say yes makes the dragon speak the riddle",
    "riddle" in out["narration"].lower() or "wise man" in out["narration"].lower(),
    out["narration"],
)
check("say yes sets is_riddle_posed", dragon.get_property("is_riddle_posed"))
check(
    "say yes clears awaiting_yes_no",
    not dragon.get_property("awaiting_yes_no"),
)
# Now the riddle is on -- the player can answer.
run(game, cap, "answer a wise man")
check("riddle answered (is_defeated)", dragon.get_property("is_defeated"))

# 11b. say no backs out cleanly.
game, cap = fresh()
teleport(game, "Treasure Trove")
dragon = game.locations["Treasure Trove"].items["dragon"]
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
out = run(game, cap, "say no")
check(
    "say no narrates a refusal",
    "coward" in out["narration"].lower() or "waste" in out["narration"].lower(),
    out["narration"],
)
check(
    "say no clears awaiting_yes_no",
    not dragon.get_property("awaiting_yes_no"),
)
check(
    "say no does NOT pose the riddle",
    not dragon.get_property("is_riddle_posed"),
)
# After saying no the player can wake the dragon again.
out = run(game, cap, "wake dragon")
check(
    "dragon can be re-woken after a refusal",
    dragon.get_property("is_challenged"),
)

# 11c. say yes outside the dragon context is gracefully rejected.
game, cap = fresh()
out = run(game, cap, "say yes")
check(
    "say yes outside context fails informatively",
    "yes to what" in out["blocked"].lower(),
    out,
)

# --------------------------------------------------------------------------
# 11d. All choose verbs are gated on the dragon's state
# --------------------------------------------------------------------------
# choose wits / choose steel reject while the dragon is asleep.
game, cap = fresh()
teleport(game, "Treasure Trove")
out = run(game, cap, "choose wits")
check(
    "choose wits rejected before wake dragon",
    bool(out["blocked"]),
    out,
)
out = run(game, cap, "choose steel")
check(
    "choose steel rejected before wake dragon",
    bool(out["blocked"]),
    out,
)
# choose sword / choose ring reject before the riddle is answered.
run(game, cap, "wake dragon")
out = run(game, cap, "choose sword")
check(
    "choose sword rejected before riddle is answered",
    bool(out["blocked"]) and "hasn't offered" in out["blocked"].lower(),
    out,
)
out = run(game, cap, "choose ring")
check(
    "choose ring rejected before riddle is answered",
    bool(out["blocked"]) and "hasn't offered" in out["blocked"].lower(),
    out,
)
# Even mid-riddle (after say yes but before answer), reward picking is closed.
run(game, cap, "choose wits")
run(game, cap, "say yes")
out = run(game, cap, "choose sword")
check(
    "choose sword still rejected during the riddle (not yet defeated)",
    bool(out["blocked"]),
    out,
)
# Once the riddle is answered, choose sword goes through and HANDS over
# the sword directly -- no follow-up ``get sword`` needed.
run(game, cap, "answer a wise man")
sword = game.locations["Treasure Trove"].items.get("sword")
assert sword is not None, "sword should still be in the trove before choose sword"
out = run(game, cap, "choose sword")
check(
    "choose sword narrates the reward",
    "sword of the fallen champion" in out["narration"].lower(),
    out["narration"],
)
check(
    "choose sword hands the sword directly to the player",
    "sword" in game.player.inventory,
)
check(
    "sword is no longer in the trove after choose sword",
    "sword" not in game.locations["Treasure Trove"].items,
)

# --------------------------------------------------------------------------
# 11e. Propose without ring at the pond is rejected, not betrothing.
# --------------------------------------------------------------------------
game, cap = fresh()
teleport(game, "Middle of the Pond")
out = run(game, cap, "propose")
check(
    "propose at pond without ring narrates empty pockets",
    "pockets are empty" in out["narration"].lower()
    or "without a ring" in out["narration"].lower(),
    out["narration"],
)
check(
    "propose at pond without ring does NOT betroth",
    not game.player.get_property("is_betrothed"),
)
check(
    "propose at pond without ring does NOT end the game",
    not game.is_game_over(),
)
# With the ring it always ends, even if Rosemary fell behind on the way.
game, cap = fresh()
teleport(game, "Middle of the Pond")
ring = game.locations["Treasure Trove"].items.get("ring")
ring.location.remove_item(ring)
game.player.add_to_inventory(ring)
out = run(game, cap, "propose")
check("propose with ring ends the game", game.is_game_over())
check("propose with ring counts as a win", game.is_won())

# --------------------------------------------------------------------------
# 12. Courtyard sword block reads ALL carry slots (wielded, worn, container)
# --------------------------------------------------------------------------
# Hand-craft a player carrying the dragon-reward sword as a WIELDED item --
# the prior buggy block check (actor.inventory only) would miss this and
# get the player arrested. With _carries_property the check now sees it.
game, cap = fresh()
teleport(game, "Courtyard")
sword = game.locations["Treasure Trove"].items["sword"]
sword.location.remove_item(sword)
game.player.add_to_inventory(sword)
game.player.wield(sword)
check("sword is in player.wielded (not .inventory)", "sword" in game.player.wielded)
check("sword is NOT in player.inventory", "sword" not in game.player.inventory)
run(game, cap, "up")
check(
    "wielding the dragon-reward sword still passes Courtyard",
    game.player.location.name == "Throne Room" and not game.is_game_over(),
    f"loc={game.player.location.name} over={game.is_game_over()}",
)
# 12b. Same idea for the catfish block: a wielded sharp axe must still let
# the player wade in.
game, cap = fresh()
teleport(game, "Action Castle")
axe = game.locations["Bend in the Road"].items["axe"]
axe.set_property("is_sharp", True)
axe.location.remove_item(axe)
game.player.add_to_inventory(axe)
game.player.wield(axe)
run(game, cap, "enter moat")
check(
    "wielding a sharp axe still survives the catfish",
    game.player.location.name == "Moat" and not game.is_game_over(),
    f"loc={game.player.location.name} over={game.is_game_over()}",
)

# --------------------------------------------------------------------------
# 13. One choose per game: a committed choice locks out the others.
# --------------------------------------------------------------------------
# 13a. After choose sword, choose ring is rejected.
game, cap = fresh()
teleport(game, "Treasure Trove")
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
run(game, cap, "say yes")
run(game, cap, "answer a wise man")
run(game, cap, "choose sword")
check(
    "choose sword put the sword in player inventory", "sword" in game.player.inventory
)
out = run(game, cap, "choose ring")
check(
    "choose ring rejected after choose sword",
    bool(out["blocked"]) and "already" in out["blocked"].lower(),
    out,
)
check(
    "ring stayed in the trove (no second reward)",
    "ring" in game.locations["Treasure Trove"].items,
)

# 13b. After choose ring, choose sword is rejected.
game, cap = fresh()
teleport(game, "Treasure Trove")
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
run(game, cap, "say yes")
run(game, cap, "answer a wise man")
run(game, cap, "choose ring")
check("choose ring put the ring in player inventory", "ring" in game.player.inventory)
# After choose ring the player is teleported to the Hermit's Cave -- no
# dragon nearby. Walk back to the trove to attempt the second pick.
teleport(game, "Treasure Trove")
out = run(game, cap, "choose sword")
check(
    "choose sword rejected after choose ring",
    bool(out["blocked"]) and "already" in out["blocked"].lower(),
    out,
)
check(
    "sword stayed in the trove (no second reward)",
    "sword" in game.locations["Treasure Trove"].items,
)

# 13c. After choose wits, choose steel is rejected.
game, cap = fresh()
teleport(game, "Treasure Trove")
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
out = run(game, cap, "choose steel")
check(
    "choose steel rejected after choose wits",
    bool(out["blocked"]) and "already" in out["blocked"].lower(),
    out,
)
check("choose steel after choose wits does NOT end the game", not game.is_game_over())

# --------------------------------------------------------------------------
# 14. say yes / say no respond to the king's champion offer.
# --------------------------------------------------------------------------
# 14a. The king offers the role via the give-response on the sword. say yes
#      wins the game.
game, cap = fresh()
teleport(game, "Throne Room")
sword = game.locations["Treasure Trove"].items.get("sword")
if sword is not None and sword.location is not None:
    sword.location.remove_item(sword)
    game.player.add_to_inventory(sword)
sword.set_property("is_dragon_reward", True)
run(game, cap, "give sword to king")
check(
    "giving the sword flags the player as offered champion",
    bool(game.player.get_property("is_offered_champion")),
)
out = run(game, cap, "say yes")
check(
    "say yes to the king narrates the champion ending",
    "champion of action castle" in out["narration"].lower(),
    out["narration"],
)
check("say yes to the king ends the game", game.is_game_over())
check("say yes to the king counts as a win", game.is_won())
check(
    "say yes marks the player as champion",
    bool(game.player.get_property("is_champion")),
)

# 14b. say no produces the cobbler ending.
game, cap = fresh()
teleport(game, "Throne Room")
sword = game.locations["Treasure Trove"].items.get("sword")
if sword is not None and sword.location is not None:
    sword.location.remove_item(sword)
    game.player.add_to_inventory(sword)
sword.set_property("is_dragon_reward", True)
run(game, cap, "give sword to king")
out = run(game, cap, "say no")
check(
    "say no to the king narrates the cobbler ending",
    "cobbler" in out["narration"].lower(),
    out["narration"],
)
check("say no to the king ends the game", game.is_game_over())

# 14c. Without the offer, say yes / say no by the king still fail informatively.
game, cap = fresh()
teleport(game, "Throne Room")
out = run(game, cap, "say yes")
check(
    "say yes with no offer fails informatively",
    "yes to what" in (out["blocked"] + out["narration"]).lower(),
    out,
)
out = run(game, cap, "say no")
check(
    "say no with no offer fails informatively",
    "no to what" in (out["blocked"] + out["narration"]).lower(),
    out,
)

# --------------------------------------------------------------------------
# 15. Wrong riddle answer is fatal; right one still wins.
# --------------------------------------------------------------------------
# 15a. Anything that isn't "answer a wise man" kills the player while the
#      riddle is on the table.
game, cap = fresh()
teleport(game, "Treasure Trove")
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
run(game, cap, "say yes")
out = run(game, cap, "answer a dragon")
check(
    "wrong riddle answer ends the game",
    game.is_game_over(),
    str(game.is_game_over()),
)
check(
    "wrong riddle answer narrates the dragon's fire",
    "burned alive" in out["narration"].lower(),
    out["narration"],
)

# 15b. The correct answer (longer phrase, longest-match-first) still wins.
game, cap = fresh()
teleport(game, "Treasure Trove")
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
run(game, cap, "say yes")
out = run(game, cap, "answer a wise man")
check(
    "correct riddle answer narrates the dragon's laugh",
    "well done" in out["narration"].lower(),
    out["narration"],
)
dragon = game.locations["Treasure Trove"].items["dragon"]
check(
    "correct riddle answer marks the dragon defeated",
    bool(dragon.get_property("is_defeated")),
)
check(
    "correct riddle answer does NOT end the game",
    not game.is_game_over(),
)

# 15c. ``answer`` with no riddle posed (e.g. before saying yes) fails
#      informatively, not lethally.
game, cap = fresh()
teleport(game, "Treasure Trove")
run(game, cap, "wake dragon")
run(game, cap, "choose wits")
out = run(game, cap, "answer foo")
check(
    "answer with no riddle on the table is rejected, not fatal",
    not game.is_game_over() and bool(out["blocked"]),
    out,
)

# --------------------------------------------------------------------------
print()
n_fail = sum(1 for r in results if r[0] == FAIL)
for status, label, detail in results:
    line = f"  [{status}] {label}"
    if status == FAIL and detail:
        line += f"  -- {detail}"
    print(line)
print()
print(f"{len(results) - n_fail}/{len(results)} checks passed")
raise SystemExit(1 if n_fail else 0)
