"""LLM-enhanced parsers for text adventure games.

Provides ``LlmParser`` (LLM-narrated parsing) and ``WebLlmParser`` (the same,
wired to the web renderer) that add LLM-powered narration, intent detection,
and entity matching on top of the base keyword parser. Both gracefully fall
back to keyword parsing when the LLM is unavailable or returns no result.

Output goes through the Message/Renderer seam (``reporting.py``): every parser
builds Messages by Channel and a Renderer decides how they look. Terminal vs.
web is just a different renderer, so the ``Web*`` classes are now thin shims:

    Parser        builds Messages -> default_renderer() (rich terminal / plain)
      └── LlmParser     same, but LLM-narrates the text first
            WebParser / WebLlmParser  install a WebRenderer + expose get_messages()

Ported from the course's hw2 solution (``gpt_parser.py``) with provider-agnostic
LLM client abstraction.
"""

from __future__ import annotations

import re

from text_adventure_games import parsing
from text_adventure_games.enums import Role
from text_adventure_games.llm_client import (
    SELECT_OPTION_TOOL,
    LlmClient,
    limit_context_length,
)
from text_adventure_games.prompt_templates import render
from text_adventure_games.reporting import Channel
from text_adventure_games.things import Character, Item, Location


class LlmParser(parsing.Parser):
    """Parser with LLM-enhanced narration and intent detection (terminal mode).

    Falls back to keyword-based parsing when LLM calls return None.
    """

    def __init__(
        self,
        game,
        llm_client: LlmClient,
        echo_commands: bool = True,
        verbose: bool = False,
        narration_style: str | None = None,
    ):
        super().__init__(game, echo_commands=echo_commands)
        self.llm = llm_client
        self.verbose = verbose
        self.narration_style = narration_style
        self._rebuild_command_descriptions()

    # ------------------------------------------------------------------
    # Command description map (for LLM intent matching)
    # ------------------------------------------------------------------

    def _rebuild_command_descriptions(self):
        """Build a map of action descriptions → action names for LLM matching."""
        self.command_descriptions = {}
        for _, action in self.actions.items():
            description = action.ACTION_DESCRIPTION
            if action.ACTION_ALIASES:
                description += " (can also be invoked with '{aliases}')".format(
                    aliases="', '".join(action.ACTION_ALIASES)
                )
            action_name = action.ACTION_NAME
            if action_name:
                self.command_descriptions[description] = action_name

    def add_action(self, action):
        super().add_action(action)
        self._rebuild_command_descriptions()

    # ------------------------------------------------------------------
    # Core LLM helpers
    # ------------------------------------------------------------------

    def _narrate(self, description: str, system_instructions: str) -> str:
        """Ask the LLM to narrate *description* using command history as context.

        Returns the LLM's narrated version, or *description* unchanged on failure.
        """
        messages = [{"role": Role.SYSTEM, "content": system_instructions}]
        context = limit_context_length(
            self.command_history,
            max_tokens=self.llm.count_tokens("") + 6000,  # leave room
            token_counter=self.llm.count_tokens,
        )
        messages.extend(context)
        if self.verbose:
            import json

            print(json.dumps(messages, indent=2))
        result = self.llm.chat(messages, max_tokens=256, temperature=1.0)
        if result:
            return result
        return description

    def _pick_option(
        self, instructions: str, options: dict, input_str: str
    ) -> object | None:
        """Ask the LLM to pick one option. Prefers structured tool calling (a
        provider-validated integer index); falls back to the legacy free-text
        'return the number' path when tool calling is unavailable or returns
        nothing usable. Returns the chosen option's value, or None."""
        options_list = list(options.keys())
        choices_str = ""
        for i, option in enumerate(options_list):
            choices_str += f"{i}. {option}\n"

        system_content = f"{instructions}\n\n{choices_str}\nReturn just the number."
        messages = [
            {"role": Role.SYSTEM, "content": system_content},
            {"role": Role.USER, "content": input_str},
        ]

        if self.verbose:
            print(
                f"{instructions}\n\n{choices_str}\nReturn just the number.\n---\n> {input_str}"
            )

        # Structured path first: a validated integer index.
        if hasattr(self.llm, "call_tool"):
            result = self.llm.call_tool(
                messages, SELECT_OPTION_TOOL, max_tokens=32, temperature=0.0
            )
            if result is not None:
                index = result.get("index")
                # Note: bool is a subclass of int in Python, so guard against a
                # stray True/False sneaking through as the index 1/0.
                if (
                    isinstance(index, int)
                    and not isinstance(index, bool)
                    and 0 <= index < len(options_list)
                ):
                    return options[options_list[index]]
                # malformed / out of range -> fall through to the free-text path

        # Free-text fallback: scrape the first number out of the prose reply.
        content = self.llm.chat(messages, max_tokens=32, temperature=0.0)
        if content is None:
            return None

        if self.verbose:
            print("---\nLLM's response was:", content)

        matches = re.findall(r"\d+", content)
        if matches:
            index = int(matches[0])
            if index >= len(options_list):
                return None
            option = options_list[index]
            return options[option]
        return None

    # ------------------------------------------------------------------
    # System instruction builders
    # ------------------------------------------------------------------

    def _ok_system_instructions(self) -> str:
        return render("narrate_ok", narration_style=self.narration_style)

    def _fail_system_instructions(self) -> str:
        return render("narrate_fail")

    def _npc_system_instructions(self) -> str:
        return render("narrate_npc", narration_style=self.narration_style)

    # ------------------------------------------------------------------
    # Output methods (narration-enhanced)
    # ------------------------------------------------------------------

    def ok(self, description: str):
        self.add_description_to_history(description)
        narrated = self._narrate(description, self._ok_system_instructions())
        self._emit(Channel.NARRATION, narrated)
        self.add_description_to_history(narrated)

    def fail(self, description: str):
        self.last_fail_message = description  # the ReAct Reflect step reads this
        self.add_description_to_history(description)
        narrated = self._narrate(description, self._fail_system_instructions())
        self._emit(Channel.BLOCKED, narrated)
        self.add_description_to_history(narrated)

    def npc_ok(self, description: str):
        self.add_description_to_history(description)
        narrated = self._narrate(description, self._npc_system_instructions())
        self._emit(Channel.NPC_NARRATION, narrated)
        self.add_description_to_history(narrated)

    # ------------------------------------------------------------------
    # Intent detection (keyword-first, LLM fallback)
    # ------------------------------------------------------------------

    def determine_intent(self, command: str, actor=None):
        """Try keyword matching first; fall back to LLM if no match."""
        intent = super().determine_intent(command, actor=actor)
        if intent is not None:
            return intent
        # LLM fallback
        instructions = render("match_intent")
        return self._pick_option(instructions, self.command_descriptions, command)

    # ------------------------------------------------------------------
    # Entity matching (LLM-enhanced)
    # ------------------------------------------------------------------

    def get_character(
        self,
        command: str,
        hint: str = None,
        split_words=None,
        position=None,
        exclude=None,
    ) -> Character:
        """Try keyword matching first; fall back to LLM for character matching."""
        result = super().get_character(
            command, hint, split_words, position, exclude=exclude
        )
        # If keyword matching returned the player (default), try LLM for a better match
        if result is self.game.player and hint:
            llm_result = self._llm_get_character(command, hint)
            if llm_result is not None:
                return llm_result
        return result

    def _llm_get_character(self, command: str, hint: str = None) -> Character | None:
        """Use LLM to match a character from the command."""
        if self.verbose:
            print("Matching a character with LLM.")
        character_descriptions = {}
        for name, character in self.game.characters.items():
            if character.location:
                description = (
                    f"{name} - {character.description} "
                    f"(currently located in {character.location.name})"
                )
            else:
                description = f"{name} - {character.description}"
            if character == self.game.player:
                description = f"The player: {character.description}"
            character_descriptions[description] = character

        instructions = render(
            "match_character", player_name=self.game.player.name, hint=hint
        )
        return self._pick_option(instructions, character_descriptions, command)

    def match_item(
        self, command: str, item_dict: dict[str, Item], hint: str = None
    ) -> Item:
        """Try keyword matching first; fall back to LLM for item matching."""
        result = super().match_item(command, item_dict, hint)
        if result is not None:
            return result
        # LLM fallback
        return self._llm_match_item(command, item_dict, hint)

    def _llm_match_item(
        self, command: str, item_dict: dict[str, Item], hint: str = None
    ) -> Item | None:
        """Use LLM to match an item from the command."""
        if self.verbose:
            print("Matching an item with LLM.")
        instructions = render("match_item", hint=hint)

        item_descriptions = {}
        for name, item in item_dict.items():
            if item.location:
                description = (
                    f"{name} - {item.description} "
                    f"(currently located in {item.location.name})"
                )
            else:
                description = f"{name} - {item.description}"
            item_descriptions[description] = item
        return self._pick_option(instructions, item_descriptions, command)

    def get_direction(self, command: str, location: Location = None) -> str:
        """Try keyword matching first; fall back to LLM for direction matching."""
        result = super().get_direction(command, location)
        if result is not None:
            return result
        # LLM fallback
        return self._llm_get_direction(command, location)

    def _llm_get_direction(self, command: str, location: Location = None) -> str | None:
        """Use LLM to match a direction from the command."""
        if self.verbose:
            print("Matching a direction with LLM.")
        instructions = render("match_direction")
        directions = {}
        if location:
            for direction, to_loc in location.connections.items():
                loc_description = f"{to_loc.name} - {to_loc.description}"
                key = f"{direction} toward {loc_description}"
                directions[key] = direction
        other_directions = {
            "'n' can mean north": "north",
            "'s' can mean south": "south",
            "'e' can mean east": "east",
            "'w' can mean west": "west",
            "'out' can mean 'go out'": "out",
            "'in' can mean 'go in'": "in",
            "'up' can mean 'go up'": "up",
            "'down' can mean 'go down'": "down",
        }
        directions.update(other_directions)
        return self._pick_option(instructions, directions, command)


# ======================================================================
# Web mode
# ======================================================================


class WebLlmParser(LlmParser):
    """Compatibility shim: an :class:`LlmParser` that renders to a
    :class:`~text_adventure_games.webapp.web_parser.WebRenderer`.

    The narration logic lives in ``LlmParser`` and the buffering in the
    renderer; this subclass only installs the web renderer and exposes
    ``get_messages()`` so the existing Flask wiring keeps working.
    """

    def __init__(
        self,
        game,
        llm_client: LlmClient,
        echo_commands: bool = False,
        verbose: bool = False,
        narration_style: str | None = None,
    ):
        # Imported here (not at module top) to avoid a webapp <-> parser import
        # cycle; the webapp package imports llm_parser.
        from text_adventure_games.webapp.web_parser import WebRenderer

        super().__init__(
            game,
            llm_client,
            echo_commands=echo_commands,
            verbose=verbose,
            narration_style=narration_style,
        )
        self.set_renderer(WebRenderer())

    def get_messages(self):
        return self.renderer.drain()
