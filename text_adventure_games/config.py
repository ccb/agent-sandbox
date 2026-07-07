"""A single, declarative config for a game/simulation: :class:`GameConfig`.

Lots of the engine's tuning knobs used to be baked into the library as module
constants, inline literals, or function-argument defaults -- the day periods in
``clock.py``, the per-turn action cap in ``things/characters.py``, the LLM agent's
``temperature``/``max_tokens`` in ``npc.py``, and so on. To change one you had to
edit our source. That's fine for us, but a pain for someone building *their* game
on top of this library.

This module gathers those knobs into one place. A game author builds a
:class:`GameConfig` once -- in Python, or loaded from a YAML/JSON file shipped with
their project -- and hands it to :class:`~text_adventure_games.games.Game`::

    from text_adventure_games.config import GameConfig

    config = GameConfig.from_file("my_game/config.yaml")
    game = Game(start, player, config=config)

Two design rules keep this safe to adopt:

* **Defaults reproduce today's behavior.** Every field defaults to the value that
  used to be hardcoded, so ``GameConfig()`` (or passing no config at all) changes
  nothing. The change is purely additive.
* **Composition, not one giant class.** The knobs are grouped into small sub-configs
  by what they affect -- :class:`AgentConfig`, :class:`EngineConfig`,
  :class:`ClockConfig`, :class:`RenderConfig` -- plus the existing
  :class:`~text_adventure_games.llm_client.LlmConfig` for the LLM connection. Each
  group is small enough to read at a glance.

See ``docs/configuration.md`` for a guide with a full sample config file.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field, fields, is_dataclass

from .llm_client import LlmConfig, LlmClient, create_llm_client
from .usage import RunLog

# These mirror the engine's historical defaults. They live here so the dataclass
# field defaults read as plain numbers (easy for a student to scan) while the
# original modules keep their own constants as the no-config fallback.


@dataclass
class AgentConfig:
    """How an LLM-driven NPC thinks (see ``npc.py``).

    Consumed by the behavior factories
    :func:`~text_adventure_games.npc.make_react_behavior` and
    :func:`~text_adventure_games.npc.make_hybrid_behavior`.
    """

    # Sampling temperature for NPC decisions. 0.0 is deterministic; higher is
    # more exploratory/varied. Was hardcoded in LLMAgent.__init__.
    temperature: float = 0.7
    # Output token budget per NPC decision -- caps cost and verbosity.
    max_tokens: int = 128
    # How many times an agent retries a command that fails its preconditions
    # before giving up for the turn (total attempts = 1 + max_retries).
    max_retries: int = 1
    # Upper bound (in in-game minutes) on an action duration an agent may claim,
    # guarding against absurd model output. Was npc._MAX_DURATION (one full day).
    max_duration: int = 24 * 60
    # Accumulated memory importance at which an agent runs a periodic reflection
    # pass (issue #84, reflection.should_reflect). Only consulted when the agent
    # actually has a reflector wired in -- with none (the default), reflection
    # never fires and behavior is unchanged. Was reflection.DEFAULT_REFLECTION_THRESHOLD.
    reflection_threshold: float = 30.0


@dataclass
class EngineConfig:
    """Turn loop, world, and trigger knobs (see ``games.py``, ``things/``)."""

    # "sequential" (player then each NPC, in order) or "simultaneous"
    # (gather -> resolve round; see turns.py). Was Game(turn_mode=...).
    turn_mode: str = "sequential"
    # Action-resolution ordering for simultaneous mode. False keeps the plain
    # initiative order; True uses turns.DEFAULT_PHASES ("talk before move before
    # fight"); a dict gives your own ``{action_name: phase_rank}`` map.
    phases: bool | dict = False
    # Print each item's special commands as hints (helpful for novices).
    give_hints: bool = True
    # Whether meta commands (INVENTORY, HELP -- actions flagged FREE_ACTION)
    # consume a game turn. False (default): they report without advancing the
    # round, so checking your pack mid-fight is not an opening for the boss.
    # True restores the classic everything-costs-time behavior.
    meta_actions_cost_turns: bool = False
    # Hard cap on actions one NPC may take in a single turn, regardless of the
    # time budget. Was things.characters.MAX_ACTIONS_PER_TURN.
    max_actions_per_turn: int = 100
    # How many recently-heard utterances a character remembers (FIFO). Was
    # things.characters.HEARD_MAX.
    heard_max: int = 5
    # How many passes the post-round trigger phase makes so a trigger can enable
    # another (cascading), before stopping. Was triggers.MAX_CASCADE_PASSES.
    cascade_passes: int = 2


@dataclass
class ClockConfig:
    """The optional in-game clock (see ``clock.py``).

    Time is opt-in: leave ``enabled`` False and the game runs with no clock, exactly
    as before. Set it True to build a :class:`~text_adventure_games.clock.GameClock`
    from these fields.
    """

    # Off by default so existing games (which have no clock) are unchanged.
    enabled: bool = False
    start_hour: int = 8
    start_minute: int = 0
    minutes_per_turn: int = 15
    # ``(start_hour, name)`` pairs naming chunks of the day. None means use
    # clock.DEFAULT_PERIODS; [] disables period names.
    periods: list | None = None


@dataclass
class RenderConfig:
    """How output looks in the terminal (see ``reporting.py``).

    ``level`` and ``no_color`` default to None, meaning "follow the environment"
    -- the ``OUTPUT_LEVEL`` and ``NO_COLOR`` env vars (or the built-in default)
    decide, exactly as before. Set them here to override the environment.
    """

    # Verbosity: "quiet" | "normal" | "verbose", or None to follow OUTPUT_LEVEL.
    level: str | None = None
    # Wrap width in columns for narration text.
    width: int = 80
    # Force the plain (no-color) renderer, or None to follow NO_COLOR.
    no_color: bool | None = None


@dataclass
class ObservabilityConfig:
    """LLM cost/usage logging (see ``usage.py``).

    Observability is opt-in. With no ``log_path`` a run still tallies token usage
    in an in-memory :class:`~text_adventure_games.usage.UsageLedger` (cheap, always
    on) but writes nothing to disk -- exactly today's behavior. Set ``log_path`` to
    also stream a per-run JSONL artifact: a ``run`` header, one ``call`` line per
    LLM call, and a ``summary`` footer of per-actor token/cost totals.
    """

    # Where to write the per-run JSONL usage log. None = no artifact (default).
    # A directory gets a timestamped ``{YYYYmmdd-HHMMSS}-{provider}.jsonl`` file;
    # a path ending in ``.jsonl``/``.json`` is used verbatim.
    log_path: str | None = None
    # Include full prompts/responses in the artifact (default: numbers only). The
    # token/cost numbers are always written; this adds the verbose transcript.
    log_prompts: bool = False
    # Hard LLM cost ceiling in USD for the run, or None (default) for no ceiling
    # (issue #183). When set, the run's UsageLedger arms a kill-switch: a driver
    # loop polls UsageLedger.over_budget() and stops once cumulative spend reaches
    # it -- a guard for unattended or scaled live runs. The in-memory tally is
    # always on, so a ceiling works with or without a log_path.
    max_cost_usd: float | None = None

    def build_run_log(
        self, *, provider=None, model=None, turn_mode=None, seed=None
    ) -> RunLog | None:
        """Create a :class:`~text_adventure_games.usage.RunLog` for this run, or
        ``None`` if logging is off (``log_path`` unset).

        A directory ``log_path`` is turned into a timestamped file name; a path
        ending in ``.jsonl``/``.json`` is used as-is. The *provider* / *model* /
        *turn_mode* / *seed* land in the artifact's ``run`` header so a run can be
        reproduced from the log alone.
        """
        if not self.log_path:
            return None
        path = self.log_path
        if not path.lower().endswith((".jsonl", ".json")):
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            path = os.path.join(path, f"{ts}-{provider or 'run'}.jsonl")
        return RunLog(
            path,
            seed=seed,
            provider=provider,
            model=model,
            turn_mode=turn_mode,
            log_prompts=self.log_prompts,
        )


@dataclass
class GameConfig:
    """The one config object a game/simulation hands to :class:`Game`.

    Compose it directly, load it from a file with :meth:`from_file`, or read the
    library's environment variables with :meth:`from_env`. Every field has a
    default that reproduces the engine's historical behavior, so an empty
    ``GameConfig()`` is a no-op.
    """

    # The LLM connection (provider, api key, model, ...). None means "no LLM";
    # reuses the existing dataclass rather than duplicating it.
    llm: LlmConfig | None = None
    agent: AgentConfig = field(default_factory=AgentConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    clock: ClockConfig = field(default_factory=ClockConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)

    # -- construction helpers ------------------------------------------------

    @classmethod
    def from_file(cls, path) -> "GameConfig":
        """Load a config from a ``.yaml``/``.yml`` or ``.json`` file.

        The file's top-level keys are the sub-config names (``llm``, ``agent``,
        ``engine``, ``clock``, ``render``, ``observability``); each maps to a dict
        of that group's fields. Any group you omit keeps its defaults. YAML needs
        ``pyyaml`` installed (it ships as a dependency); JSON needs nothing extra.
        """
        path = os.fspath(path)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        lower = path.lower()
        if lower.endswith((".yaml", ".yml")):
            try:
                import yaml
            except ImportError as e:  # pragma: no cover - depends on optional dep
                raise ImportError(
                    "Reading a YAML config needs pyyaml (`pip install pyyaml`), "
                    "or use a .json config file instead."
                ) from e
            data = yaml.safe_load(text) or {}
        elif lower.endswith(".json"):
            data = json.loads(text) if text.strip() else {}
        else:
            raise ValueError(
                f"Unsupported config file type: {path!r} (use .yaml, .yml, or .json)"
            )
        if not isinstance(data, dict):
            raise ValueError(
                f"Config file {path!r} must contain a mapping at the top level"
            )
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "GameConfig":
        """Build a config from a plain dict (the shape :meth:`from_file` parses)."""
        unknown = set(data) - {
            "llm",
            "agent",
            "engine",
            "clock",
            "render",
            "observability",
        }
        if unknown:
            raise ValueError(
                f"Unknown config section(s): {sorted(unknown)}. "
                "Valid sections: llm, agent, engine, clock, render, observability."
            )
        llm_data = data.get("llm")
        if llm_data is not None:
            llm = _build(LlmConfig, llm_data, "llm")
        else:
            llm = None
        return cls(
            llm=llm,
            agent=_build(AgentConfig, data.get("agent", {}), "agent"),
            engine=_build(EngineConfig, data.get("engine", {}), "engine"),
            clock=_build(ClockConfig, data.get("clock", {}), "clock"),
            render=_build(RenderConfig, data.get("render", {}), "render"),
            observability=_build(
                ObservabilityConfig,
                data.get("observability", {}),
                "observability",
            ),
        )

    @classmethod
    def from_env(cls) -> "GameConfig":
        """Build a config from the library's environment variables.

        Reads the same ``LLM_*`` vars as
        :func:`~text_adventure_games.llm_client.client_from_env` for the LLM
        section -- including the resilience knobs ``LLM_MAX_RETRIES`` and
        ``LLM_API_TIMEOUT_SEC`` -- plus ``OUTPUT_LEVEL`` and ``NO_COLOR`` for
        rendering and ``LLM_LOG`` / ``LLM_LOG_PROMPTS`` / ``LLM_MAX_COST`` for the
        usage log and cost ceiling. Anything unset keeps its default.
        """
        config = cls()
        provider = os.environ.get("LLM_PROVIDER")
        if provider:
            config.llm = LlmConfig(
                provider=provider,
                api_key=os.environ.get("LLM_API_KEY"),
                model=os.environ.get("LLM_MODEL"),
                base_url=os.environ.get("LLM_BASE_URL"),
                verbose=os.environ.get("LLM_VERBOSE", "").lower() in ("1", "true"),
                max_retries=int(
                    os.environ.get("LLM_MAX_RETRIES", LlmConfig.max_retries)
                ),
                timeout_sec=float(
                    os.environ.get("LLM_API_TIMEOUT_SEC", LlmConfig.timeout_sec)
                ),
            )
        level = os.environ.get("OUTPUT_LEVEL", "").strip().lower()
        if level in ("quiet", "normal", "verbose"):
            config.render.level = level
        if os.environ.get("NO_COLOR"):
            config.render.no_color = True
        log_path = os.environ.get("LLM_LOG")
        if log_path:
            config.observability.log_path = log_path
        if os.environ.get("LLM_LOG_PROMPTS", "").lower() in ("1", "true"):
            config.observability.log_prompts = True
        # A bad value fails loud rather than silently disabling a safety guard.
        max_cost = os.environ.get("LLM_MAX_COST")
        if max_cost:
            config.observability.max_cost_usd = float(max_cost)
        return config

    def to_dict(self) -> dict:
        """Serialize to a plain, JSON-able dict (inverse of :meth:`from_dict`)."""
        out = {
            "agent": _asdict(self.agent),
            "engine": _asdict(self.engine),
            "clock": _asdict(self.clock),
            "render": _asdict(self.render),
            "observability": _asdict(self.observability),
        }
        if self.llm is not None:
            llm = _asdict(self.llm)
            # provider may be an LlmProvider enum; store its plain string value.
            if llm.get("provider") is not None:
                llm["provider"] = str(llm["provider"])
            out["llm"] = llm
        return out

    def build_llm_client(self) -> LlmClient | None:
        """Create an LLM client from :attr:`llm`, or None if it isn't set.

        A convenience for game authors and the web app, which wire NPC behaviors
        themselves; ``Game`` does not auto-create clients.
        """
        if self.llm is None:
            return None
        return create_llm_client(self.llm)

    def build_run_log(self, **header) -> RunLog | None:
        """Create a per-run usage log from :attr:`observability`, or ``None`` if
        logging is off (``observability.log_path`` unset).

        A thin convenience that forwards to
        :meth:`ObservabilityConfig.build_run_log`; pass ``provider=`` / ``model=``
        / ``turn_mode=`` / ``seed=`` for the artifact's ``run`` header.
        """
        return self.observability.build_run_log(**header)


def _build(dataclass_type, data, section_name):
    """Construct *dataclass_type* from *data*, rejecting unknown keys clearly."""
    if not isinstance(data, dict):
        raise ValueError(f"Config section {section_name!r} must be a mapping")
    valid = {f.name for f in fields(dataclass_type)}
    unknown = set(data) - valid
    if unknown:
        raise ValueError(
            f"Unknown key(s) in '{section_name}' config: {sorted(unknown)}. "
            f"Valid keys: {sorted(valid)}."
        )
    return dataclass_type(**data)


def _asdict(obj):
    """Shallow dataclass -> dict (we only nest one level, so this is enough)."""
    if not is_dataclass(obj):
        return obj
    return {f.name: getattr(obj, f.name) for f in fields(obj)}
