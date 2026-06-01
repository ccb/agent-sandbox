from __future__ import annotations

"""ReAct loop skeleton for LLM-driven NPC behavior.

This module provides a pattern for giving NPCs autonomous behavior powered by
a large language model. The game author supplies an LLM client; this module
handles observation, prompting, action routing, and retry on failure.

Supports both the ``LlmClient`` protocol (with ``chat()`` method) and plain
callables ``(str) -> str`` for backwards compatibility.

Usage::

    from text_adventure_games.npc import make_react_behavior, make_hybrid_behavior

    # With LlmClient protocol
    troll.set_behavior(make_react_behavior(llm_client))

    # Hybrid: tries LLM first, falls back to scripted
    troll.set_behavior(make_hybrid_behavior(llm_client, make_troll_behavior()))
"""


def build_npc_context(character, game) -> str:
    """Assemble an observation prompt describing what the NPC can perceive.

    Combines the character's persona with game.describe_for() (which provides
    location, exits, items, other characters, inventory, and available actions)
    and recent command history.

    Returns a string suitable for inclusion in an LLM prompt.
    """
    lines = []

    # Full environment observation from the game engine
    lines.append(game.describe_for(character))

    # Recent command history (last 5 exchanges)
    history = game.parser.command_history[-10:]
    if history:
        lines.append("")
        lines.append("Recent events:")
        for entry in history:
            role = entry["role"]
            content = entry["content"]
            prefix = "  Player:" if role == "user" else "  Game:"
            lines.append(f"{prefix} {content[:200]}")

    return "\n".join(lines)


def _build_system_message(character) -> str:
    """Build the system message containing the NPC's persona."""
    lines = [f"You are {character.name}, an NPC in a text adventure game."]
    if character.persona:
        lines.append(f"Persona: {character.persona}")
    lines.append(
        "Based on your persona and the current situation, choose a single game "
        "command to execute. Respond with ONLY the command, nothing else. "
        "Examples: 'attack player', 'go north', 'take sword'."
    )
    return "\n".join(lines)


def _call_llm(llm_client, character, prompt) -> str | None:
    """Call the LLM, supporting both LlmClient protocol and plain callables."""
    if hasattr(llm_client, "chat"):
        system_msg = _build_system_message(character)
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]
        return llm_client.chat(messages, max_tokens=64, temperature=0.7)
    else:
        # Legacy callable: (str) -> str
        full_prompt = (
            f"You are {character.name}.\n"
            f"{'Persona: ' + character.persona if character.persona else ''}\n\n"
            f"{prompt}\n\n"
            "Based on your persona and the current situation, what single game "
            "command would you like to execute? Respond with ONLY the command, "
            "nothing else.\nCommand:"
        )
        return llm_client(full_prompt)


def react_behavior(character, game, llm_client, max_retries=1):
    """Full ReAct loop: Observe -> Think -> Act -> Handle failure.

    Args:
        character: The NPC Character instance.
        game: The Game instance.
        llm_client: An ``LlmClient`` (with ``chat()`` method) or a plain
            callable ``(str) -> str``.
        max_retries: How many times to retry if the chosen action fails.
    """
    context = build_npc_context(character, game)

    for attempt in range(1 + max_retries):
        if attempt == 0:
            prompt = context
        else:
            prompt = (
                f"{context}\n\n"
                f"Your previous command '{command}' failed. "
                "Choose a different action."
            )

        response = _call_llm(llm_client, character, prompt)
        if response is None:
            return

        command = response.strip().split("\n")[0].strip()
        if not command:
            return

        # Auto-prepend character name so the parser routes correctly
        if not command.lower().startswith(character.name.lower()):
            command = f"{character.name} {command}"

        success = game.parser.parse_command(command)
        if success:
            return


def make_react_behavior(llm_client, max_retries=1):
    """Factory that returns a behavior function suitable for Character.set_behavior().

    Args:
        llm_client: An ``LlmClient`` (with ``chat()`` method) or a plain
            callable ``(str) -> str``.
        max_retries: How many times to retry on action failure.

    Returns:
        A callable with signature (character, game) -> None.
    """

    def behavior(character, game):
        react_behavior(character, game, llm_client, max_retries=max_retries)

    return behavior


def make_hybrid_behavior(llm_client, scripted_behavior, max_retries=1):
    """Factory that tries LLM ReAct first, falls back to scripted on failure.

    Args:
        llm_client: An ``LlmClient`` (with ``chat()`` method) or a plain
            callable ``(str) -> str``.
        scripted_behavior: A callable ``(character, game) -> None`` to use as
            fallback when the LLM fails or returns nothing.
        max_retries: How many times to retry the LLM on action failure.

    Returns:
        A callable with signature (character, game) -> None.
    """

    def behavior(character, game):
        context = build_npc_context(character, game)

        for attempt in range(1 + max_retries):
            if attempt == 0:
                prompt = context
            else:
                prompt = (
                    f"{context}\n\n"
                    f"Your previous command '{command}' failed. "
                    "Choose a different action."
                )

            response = _call_llm(llm_client, character, prompt)
            if response is None:
                # LLM failed, use scripted fallback
                scripted_behavior(character, game)
                return

            command = response.strip().split("\n")[0].strip()
            if not command:
                scripted_behavior(character, game)
                return

            # Auto-prepend character name so the parser routes correctly
            if not command.lower().startswith(character.name.lower()):
                command = f"{character.name} {command}"

            success = game.parser.parse_command(command)
            if success:
                return

        # All retries exhausted, fall back to scripted
        scripted_behavior(character, game)

    return behavior
