"""Custom parser for the UPenn boil-water simulation (#300).

The engine's ``Parser.determine_intent`` (text_adventure_games/parsing.py,
~line 296-302) matches EAT with a substring check -- ``"ate " in command`` --
rather than a word-boundary check. That substring appears inside "activate",
so "activate stove" (and "deactivate stove") mis-route to EAT before they
ever reach the generic action-name fallback that would otherwise resolve
them correctly.

``PennParser`` is wired for every world built via ``build_world`` (see
``build_world.py``), including Smallville -- not just the boil-water demo --
so it needs to be a safe drop-in replacement for the engine parser everywhere.
Rather than re-implementing ``determine_intent`` end to end, it overrides only
enough to catch the two device verbs before the buggy EAT check and delegates
every other command to ``Parser.determine_intent`` unchanged. That keeps this
override's behavior identical to the engine parser except for commands that
start with "activate"/"deactivate" (which previously mis-routed to EAT), by
construction rather than by keeping two copies of the keyword chain in sync.

The proper fix -- word-boundary matching in the engine's own EAT check -- is
tracked upstream in issue #464; once that lands this override can likely be
retired.
"""

from text_adventure_games.parsing import Parser


class PennParser(Parser):
    """Parser subclass that fixes the "ate " substring collision with
    "activate"/"deactivate" and otherwise delegates to the engine parser."""

    def determine_intent(self, command: str, actor=None):
        normalized = command.lower()
        if normalized == "activate" or normalized.startswith("activate "):
            return "activate"
        if normalized == "deactivate" or normalized.startswith("deactivate "):
            return "deactivate"
        return super().determine_intent(command, actor=actor)
