"""Module scaffolding: assembles the final build_game() Python source.

This is the heaviest template -- it composes the Game subclass, all custom
Action classes, all Block classes, NPC behavior factories, and the
build_game() entry point into one Python module mirroring the structure of
``notebooks/hw1_solution/action_castle.py``.
"""

from __future__ import annotations

from ._common import python_class_name, q as _q
from ..spec import legal_command_hints
from . import ACTION_EMITTERS, BLOCK_EMITTERS

# ----------------------------------------------------------------------
# is_won() emission from the predicate DSL
# ----------------------------------------------------------------------


def _emit_is_won_body(wc, indent: str = "        ") -> str:
    """Render a WinCondition as the body of ``Game.is_won()``."""
    expr = _win_condition_expr(wc)
    ok_msg = wc.ok_message or ""
    # ``is_won`` is called multiple times per round (after each NPC turn,
    # before the trigger phase, and again in ``game_loop``). Emitting the
    # ok-message naively from ``is_won`` therefore prints it 2-3 times.
    # Latching ``self.game_over`` makes the short-circuit at the top of
    # ``Game.is_game_over`` skip subsequent calls, so the message fires
    # exactly once.
    if wc.kind == "any_character_property":
        prop = _q(wc.property)
        equals_repr = (
            _q(wc.equals)
            if not isinstance(wc.equals, bool)
            else ("True" if wc.equals else "False")
        )
        ok_repr = _q(ok_msg) if ok_msg else _q("{name} wins!")
        return (
            f"{indent}if self.game_over:\n"
            f"{indent}    return True\n"
            f"{indent}for name, character in self.characters.items():\n"
            f"{indent}    if character.get_property({prop}) == {equals_repr}:\n"
            f"{indent}        msg = {ok_repr}.format(name=character.name.title())\n"
            f"{indent}        self.game_over = True\n"
            f"{indent}        self.game_over_description = msg\n"
            f"{indent}        self.parser.ok(msg)\n"
            f"{indent}        return True\n"
            f"{indent}return False"
        )
    # Generic boolean expression form for the other kinds.
    if ok_msg:
        return (
            f"{indent}if self.game_over:\n"
            f"{indent}    return True\n"
            f"{indent}if {expr}:\n"
            f"{indent}    self.game_over = True\n"
            f"{indent}    self.game_over_description = {_q(ok_msg)}\n"
            f"{indent}    self.parser.ok({_q(ok_msg)})\n"
            f"{indent}    return True\n"
            f"{indent}return False"
        )
    return f"{indent}return bool({expr})"


def _win_condition_expr(wc) -> str:
    """Return a boolean Python expression evaluating the WinCondition."""
    if wc.kind == "player_at_location":
        return f"self.player.location.name == {_q(wc.location)}"
    if wc.kind == "player_has_item":
        return f"{_q(wc.item)} in self.player.inventory"
    if wc.kind == "flag":
        return f"bool(self.player.get_property({_q(wc.name)}))"
    if wc.kind == "all_of":
        return " and ".join(f"({_win_condition_expr(c)})" for c in wc.children or [])
    if wc.kind == "any_of":
        return " or ".join(f"({_win_condition_expr(c)})" for c in wc.children or [])
    if wc.kind == "any_character_property":
        return (
            f"any(c.get_property({_q(wc.property)}) == "
            f"{_py_value(wc.equals)} for c in self.characters.values())"
        )
    raise ValueError(f"unknown win_condition kind {wc.kind!r}")


def _py_value(v) -> str:
    """Render a Python literal for a primitive, dict, or list."""
    if isinstance(v, bool):
        return "True" if v else "False"
    if v is None:
        return "None"
    if isinstance(v, dict):
        inner = ", ".join(f"{_q(k)}: {_py_value(val)}" for k, val in v.items())
        return "{" + inner + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_py_value(x) for x in v) + "]"
    return _q(v)


# ----------------------------------------------------------------------
# NPC behaviors -- the make_<character>_behavior() factories.
# ----------------------------------------------------------------------


def _emit_behavior_factory(character) -> str:
    """Render the make_<name>_behavior() factory for a character.

    Mirrors the closure pattern in ``notebooks/hw1_solution/action_castle.py``
    (``make_troll_behavior``, ``make_guard_behavior``, ``make_ghost_behavior``):
    captures a state dict, formats one of N escalating commands by turn
    index, and falls back to a final command thereafter.
    """
    name = character.name
    safe = _safe_factory_name(name)
    b = character.behavior
    if b is None or b.kind == "none":
        return ""
    if b.kind != "escalating_commands":
        return ""

    # Each command in commands[] and the fallback are auto-prefixed with the
    # character name so the parser's substring-based actor resolution sees
    # the right subject when parse_command runs without an explicit actor.
    # The prefix is unconditional: an NPC whose verb happens to start with
    # its own name (e.g. ghost / "ghost touch") still needs the actor token
    # ahead of the verb -- matches the reference's "ghost ghost touch X".
    def _prefix(cmd: str) -> str:
        return f"{name} {cmd}"

    commands_repr = (
        "[\n" + "".join(f"        {_q(_prefix(c))},\n" for c in b.commands) + "    ]"
    )
    fallback_repr = _q(_prefix(b.fallback)) if b.fallback else "None"
    guard = b.guard

    lines = [
        f"def make_{safe}_behavior():",
        f'    """Factory for the {name!r} character. Escalates over turns; '
        'state lives in a closure (matching the reference pattern)."""',
        f"    commands = {commands_repr}",
        f"    fallback = {fallback_repr}",
        '    state = {"turns_present": 0}',
        "",
        "    def behavior(character, game):",
        "        player = game.player",
        "        if player.location is not character.location:",
        '            state["turns_present"] = 0',
        "            return",
    ]
    if guard:
        eq = _py_value(guard.equals)
        prop = _q(guard.property)
        lines.append(f"        if character.get_property({prop}) != {eq}:")
        lines.append("            return")
    lines += [
        '        state["turns_present"] += 1',
        '        idx = state["turns_present"] - 1',
        "        if idx >= len(commands):",
        "            if fallback:",
        "                game.parser.parse_command(",
        "                    fallback.format(player=player.name),",
        "                    actor=character,",
        "                )",
        "            return",
        "        cmd = commands[idx].format(player=player.name)",
        "        game.parser.parse_command(cmd, actor=character)",
        "",
        "    return behavior",
    ]
    return "\n".join(lines) + "\n"


def _safe_factory_name(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_") or "unnamed"


# ----------------------------------------------------------------------
# build_game() body assembly
# ----------------------------------------------------------------------


def _safe_var(s: str) -> str:
    """Turn a name like 'Garden Path' into a Python identifier 'garden_path'."""
    out = []
    prev_us = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    return "".join(out).strip("_") or "thing"


def _emit_locations(spec) -> tuple[str, dict[str, str]]:
    """Returns the location-construction block and a {name -> var_name} map."""
    var_map: dict[str, str] = {}
    used: set[str] = set()
    lines = []
    for loc in spec.locations:
        base = _safe_var(loc.name)
        var = base
        i = 2
        while var in used:
            var = f"{base}_{i}"
            i += 1
        used.add(var)
        var_map[loc.name] = var
        lines.append(
            f"    {var} = things.Location({_q(loc.name)}, {_q(loc.description)})"
        )
        for k, v in loc.properties.items():
            lines.append(f"    {var}.set_property({_q(k)}, {_py_value(v)})")
    return "\n".join(lines), var_map


def _emit_connections(spec, var_map) -> str:
    lines = []
    for loc in spec.locations:
        src = var_map[loc.name]
        for ex in loc.exits:
            dst = var_map[ex.to]
            args = [_q(ex.direction), dst]
            td = ex.travel_description or ""
            if td:
                args.append(_q(td))
            if ex.reverse_direction is not None:
                # Keep travel_description positional only when present so the
                # short form (no description) stays compact.
                if not td:
                    args.append('""')
                args.append(f"reverse_direction={_q(ex.reverse_direction)}")
                if ex.reverse_travel_description:
                    args.append(
                        "reverse_travel_description="
                        f"{_q(ex.reverse_travel_description)}"
                    )
            lines.append(f"    {src}.add_connection({', '.join(args)})")
    return "\n".join(lines)


def _emit_world_items(spec, var_map) -> tuple[str, dict[str, str]]:
    """Build items that live at a location at start. Returns the block and a
    map from item name to Python var name. Owned items (in NPC/player inventory)
    are constructed later, inside the character block.
    """
    item_var: dict[str, str] = {}
    used = set(var_map.values())
    lines = []
    for item in spec.items:
        if item.at.owner:
            continue  # owned items handled in character block
        base = _safe_var(item.name)
        var = base
        i = 2
        while var in used:
            var = f"{base}_{i}"
            i += 1
        used.add(var)
        item_var[item.name] = var
        if item.examine_text:
            lines.append(
                f"    {var} = things.Item({_q(item.name)}, {_q(item.description)}, {_q(item.examine_text)})"
            )
        else:
            lines.append(
                f"    {var} = things.Item({_q(item.name)}, {_q(item.description)})"
            )
        for k, v in item.properties.items():
            lines.append(f"    {var}.set_property({_q(k)}, {_py_value(v)})")
        kept, _ = legal_command_hints(spec, item.command_hints)
        for hint in kept:
            lines.append(f"    {var}.add_command_hint({_q(hint)})")
        if item.read_text:
            lines.append(f"    {var}.read_text = {_q(item.read_text)}")
        _emit_use_responses(lines, var, item.use_responses)
        if item.at.location:
            loc_var = var_map[item.at.location]
            lines.append(f"    {loc_var}.add_item({var})")
    return "\n".join(lines), item_var


def _emit_characters(spec, var_map, item_var) -> tuple[str, dict[str, str]]:
    char_var: dict[str, str] = {}
    used = set(var_map.values()) | set(item_var.values())
    lines = []
    for char in spec.characters:
        base = _safe_var(char.name)
        var = base
        i = 2
        while var in used:
            var = f"{base}_{i}"
            i += 1
        used.add(var)
        char_var[char.name] = var
        lines.append("")
        lines.append(f"    {var} = things.Character(")
        lines.append(f"        name={_q(char.name)},")
        lines.append(f"        description={_q(char.description)},")
        lines.append(f"        persona={_q(char.persona)},")
        lines.append("    )")
        for k, v in char.properties.items():
            lines.append(f"    {var}.set_property({_q(k)}, {_py_value(v)})")
        # Inventory: construct owned items inline.
        for inv_name in char.inventory:
            owned = _find_item_spec(spec, inv_name)
            if not owned:
                # The validator catches this; if we got here we just skip.
                continue
            ivar_base = _safe_var(inv_name)
            ivar = ivar_base
            j = 2
            while ivar in used:
                ivar = f"{ivar_base}_{j}"
                j += 1
            used.add(ivar)
            item_var[inv_name] = ivar
            if owned.examine_text:
                lines.append(
                    f"    {ivar} = things.Item({_q(owned.name)}, {_q(owned.description)}, {_q(owned.examine_text)})"
                )
            else:
                lines.append(
                    f"    {ivar} = things.Item({_q(owned.name)}, {_q(owned.description)})"
                )
            for k, v in owned.properties.items():
                lines.append(f"    {ivar}.set_property({_q(k)}, {_py_value(v)})")
            kept, _ = legal_command_hints(spec, owned.command_hints)
            for hint in kept:
                lines.append(f"    {ivar}.add_command_hint({_q(hint)})")
            lines.append(f"    {var}.add_to_inventory({ivar})")
        # Place character at their starting location.
        lines.append(f"    {var_map[char.at]}.add_character({var})")
        # Give-response hooks (fired by the engine's Give action when this
        # character receives the named item under matching conditions).
        for gr in char.give_responses:
            kwargs = []
            if gr.requires_recipient_properties:
                kwargs.append(
                    "requires_recipient_properties="
                    f"{_py_value(gr.requires_recipient_properties)}"
                )
            if gr.sets_recipient_properties:
                kwargs.append(
                    "sets_recipient_properties="
                    f"{_py_value(gr.sets_recipient_properties)}"
                )
            if gr.sets_giver_properties:
                kwargs.append(
                    "sets_giver_properties=" f"{_py_value(gr.sets_giver_properties)}"
                )
            if gr.sets_item_properties:
                kwargs.append(
                    "sets_item_properties=" f"{_py_value(gr.sets_item_properties)}"
                )
            if gr.returns_to_giver:
                kwargs.append("returns_to_giver=True")
            trailing = ("," + " " + ", ".join(kwargs)) if kwargs else ""
            lines.append(
                f"    {var}.add_give_response("
                f"item={_q(gr.item)}, "
                f"response_text={_q(gr.response_text)}"
                f"{trailing})"
            )
        # Talk/ask dialogue: greeting + topic table.
        if char.greeting:
            lines.append(f"    {var}.set_greeting({_q(char.greeting)})")
        for topic, response in char.dialogue.items():
            lines.append(f"    {var}.add_dialogue({_q(topic)}, {_q(response)})")
        # examine_text: shown by the engine's Examine action when targeting
        # this character (mirrors Item.examine_text). Empty falls back to
        # the character's short description in the room listing.
        if char.examine_text:
            lines.append(f"    {var}.examine_text = {_q(char.examine_text)}")
        # Use-on hooks (fired by Use_On when someone uses a tool on this
        # character). See UseResponseSpec; shape mirrors items'.
        _emit_use_responses(lines, var, char.use_responses)
    return "\n".join(lines), char_var


def _emit_use_responses(lines, target_var, use_responses):
    """Append ``target_var.add_use_response(...)`` calls for every entry."""
    for ur in use_responses:
        kwargs = [f"response_text={_q(ur.response_text)}"]
        if ur.requires_tool_properties:
            kwargs.append(
                f"requires_tool_properties={_py_value(ur.requires_tool_properties)}"
            )
        if ur.requires_target_properties:
            kwargs.append(
                "requires_target_properties="
                f"{_py_value(ur.requires_target_properties)}"
            )
        if ur.sets_tool_properties:
            kwargs.append(f"sets_tool_properties={_py_value(ur.sets_tool_properties)}")
        if ur.sets_target_properties:
            kwargs.append(
                f"sets_target_properties={_py_value(ur.sets_target_properties)}"
            )
        if ur.consumes_tool:
            kwargs.append("consumes_tool=True")
        lines.append(
            f"    {target_var}.add_use_response(tool={_q(ur.tool)}, "
            + ", ".join(kwargs)
            + ")"
        )


def _find_item_spec(spec, name):
    for item in spec.items:
        if item.name == name:
            return item
    return None


def _emit_blocks(spec, var_map, item_var, char_var) -> tuple[str, list[str]]:
    """Emit the block-instantiation code inside build_game() and return the
    list of block class names (used in module.py to know which classes to
    insert in the file)."""
    lines = []
    classes_used: list[str] = []
    for block in spec.blocks:
        cls = (
            python_class_name(block.name) if block.name else python_class_name(block.id)
        )
        classes_used.append(cls)
        loc_var = var_map[block.at_location]
        if block.template == "property_block":
            obs = block.obstacle
            obs_var = (
                char_var[obs.name] if obs.kind == "character" else item_var[obs.name]
            )
            lines.append(f"    {_safe_var(block.id)} = {cls}({loc_var}, {obs_var})")
            lines.append(
                f"    {loc_var}.add_block({_q(block.direction)}, {_safe_var(block.id)})"
            )
        elif block.template == "darkness_block":
            lines.append(f"    {_safe_var(block.id)} = {cls}({loc_var})")
            lines.append(
                f"    {loc_var}.add_block({_q(block.direction)}, {_safe_var(block.id)})"
            )
    return "\n".join(lines), classes_used


def _emit_player(spec, var_map, item_var=None) -> str:
    if item_var is None:
        item_var = {}
    p = spec.player
    lines = [
        "    player = things.Character(",
        f"        name={_q(p.name)},",
        f"        description={_q(p.description)},",
        f"        persona={_q(p.persona)},",
        "    )",
    ]
    for k, v in p.properties.items():
        lines.append(f"    player.set_property({_q(k)}, {_py_value(v)})")
    if not p.properties.get("character_type"):
        # Sensible default if the spec didn't specify.
        lines.append('    player.set_property("character_type", "human")')
    for inv in p.inventory:
        var = _safe_var(inv.name)
        # Register player-owned items in item_var so blocks emitted after this
        # call can resolve item-obstacle references that point at player gear.
        item_var[inv.name] = var
        if inv.examine_text:
            lines.append(
                f"    {var} = things.Item({_q(inv.name)}, {_q(inv.description)}, {_q(inv.examine_text)})"
            )
        else:
            lines.append(
                f"    {var} = things.Item({_q(inv.name)}, {_q(inv.description)})"
            )
        for k, v in inv.properties.items():
            lines.append(f"    {var}.set_property({_q(k)}, {_py_value(v)})")
        kept, _ = legal_command_hints(spec, inv.command_hints)
        for hint in kept:
            lines.append(f"    {var}.add_command_hint({_q(hint)})")
        lines.append(f"    player.add_to_inventory({var})")
    return "\n".join(lines)


def _emit_behavior_wiring(spec, char_var) -> str:
    escalating = [
        c
        for c in spec.characters
        if c.behavior and c.behavior.kind == "escalating_commands"
    ]
    follow = [c for c in spec.characters if c.behavior and c.behavior.kind == "follow"]
    if not escalating and not follow:
        return ""
    lines = []
    # Follow behaviors are pure scripted (no LLM), identical with or without a
    # client, so they wire up unconditionally. The follow trigger property
    # defaults to "is_following"; a guard can name a different one.
    for c in follow:
        var = char_var[c.name]
        prop = c.behavior.guard.property if c.behavior.guard else "is_following"
        lines.append(f"    {var}.set_behavior(make_follow_behavior({_q(prop)}))")
    if escalating:
        lines.append("    if llm_client:")
        for c in escalating:
            safe = _safe_factory_name(c.name)
            var = char_var[c.name]
            lines.append(
                f"        {var}.set_behavior(make_hybrid_behavior(llm_client, make_{safe}_behavior()))"
            )
        lines.append("    else:")
        for c in escalating:
            safe = _safe_factory_name(c.name)
            var = char_var[c.name]
            lines.append(f"        {var}.set_behavior(make_{safe}_behavior())")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Top-level module emission
# ----------------------------------------------------------------------


def emit_module(spec) -> str:
    """Emit the full Python source for a build_game() module."""
    class_name = spec.class_name
    game_name = spec.game_name

    # Custom action classes
    action_class_blocks = []
    action_class_names = []
    for action in spec.custom_actions:
        emitter = ACTION_EMITTERS[action.template]
        src = emitter(action.id, action.params)
        action_class_blocks.append(src)
        action_class_names.append(python_class_name(action.id))

    # Block classes
    block_class_blocks = []
    seen_block_classes: set[str] = set()
    for block in spec.blocks:
        emitter = BLOCK_EMITTERS[block.template]
        src = emitter(block)
        cls = (
            python_class_name(block.name) if block.name else python_class_name(block.id)
        )
        if cls in seen_block_classes:
            continue
        seen_block_classes.add(cls)
        block_class_blocks.append(src)

    # Behavior factories
    behavior_blocks = [_emit_behavior_factory(c) for c in spec.characters]
    behavior_blocks = [b for b in behavior_blocks if b]

    # build_game() body
    locations_src, var_map = _emit_locations(spec)
    connections_src = _emit_connections(spec, var_map)
    items_src, item_var = _emit_world_items(spec, var_map)
    characters_src, char_var = _emit_characters(spec, var_map, item_var)
    player_src = _emit_player(spec, var_map, item_var)
    blocks_src, _ = _emit_blocks(spec, var_map, item_var, char_var)
    behavior_wiring = _emit_behavior_wiring(spec, char_var)

    # Game subclass
    is_won_body = _emit_is_won_body(spec.win_condition)
    game_class = (
        f"class {class_name}(games.Game):\n"
        f"    def __init__(self, start_at, player, characters=None, custom_actions=None):\n"
        f"        super().__init__(start_at, player, characters, custom_actions)\n"
        f"\n"
        f"    def is_won(self) -> bool:\n"
        f"{is_won_body}\n"
    )

    # Custom-actions list passed to the Game subclass.
    custom_actions_list = (
        "    custom_actions = [\n"
        + "".join(f"        {n},\n" for n in action_class_names)
        + "    ]\n"
    )

    # Characters list passed to the Game subclass.
    character_var_list = (
        "    characters = [\n"
        + "".join(f"        {char_var[c.name]},\n" for c in spec.characters)
        + "    ]\n"
    )

    # Only import the behavior factories the game actually wires up, so the
    # generated module has no unused imports.
    npc_imports = ["make_hybrid_behavior"]
    if any(c.behavior and c.behavior.kind == "follow" for c in spec.characters):
        npc_imports.append("make_follow_behavior")

    parts = [
        f'"""Auto-generated game module for {game_name!r}.\n\n'
        f"Source: {spec.source.pdf} (pages {spec.source.pages[0]}-{spec.source.pages[1]}).\n"
        f"This module is regenerated by ``text_adventure_games.codegen`` -- edit\n"
        f'the GameSpec or templates, not this file.\n"""\n',
        "from text_adventure_games import games, things, actions, blocks",
        f"from text_adventure_games.npc import {', '.join(npc_imports)}",
        "",
        game_class,
        "",
        "# ---- Custom Actions ----",
        "",
    ]
    for block in action_class_blocks:
        parts.append(block)
        parts.append("")
    parts.append("# ---- Custom Blocks ----")
    parts.append("")
    for block in block_class_blocks:
        parts.append(block)
        parts.append("")
    if behavior_blocks:
        parts.append("# ---- NPC Behavior Factories ----")
        parts.append("")
        for block in behavior_blocks:
            parts.append(block)
            parts.append("")
    parts.append("# ---- build_game ----")
    parts.append("")
    parts.append(f"def build_game(llm_client=None) -> {class_name}:")
    parts.append(locations_src)
    parts.append("")
    parts.append(connections_src)
    parts.append("")
    parts.append(items_src)
    parts.append("")
    parts.append(characters_src)
    parts.append("")
    parts.append(player_src)
    parts.append("")
    if behavior_wiring:
        parts.append(behavior_wiring)
        parts.append("")
    parts.append(blocks_src)
    parts.append("")
    parts.append(character_var_list)
    parts.append(custom_actions_list)
    parts.append(
        f"    return {class_name}({var_map[spec.start_at]}, player, characters, custom_actions)\n"
    )
    parts.append("")
    parts.append('if __name__ == "__main__":')
    parts.append("    build_game().game_loop()")
    return "\n".join(parts) + "\n"
