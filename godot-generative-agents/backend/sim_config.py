"""A single, declarative config for the generative-agents sim: :class:`SimulationConfig`.

This is the generative-agents counterpart to the engine's
:class:`~text_adventure_games.config.GameConfig`. Where ``GameConfig`` gathers the
*engine's* knobs (LLM, agent, turn loop, clock, render, observability),
``SimulationConfig`` gathers the *sim's* knobs and **composes** ``GameConfig`` rather
than forking it. Every section is **world-agnostic** -- it configures the shared agent
engine, so it applies to whatever world the sim runs (the primary world is the UPenn
campus):

* ``game`` -- an embedded :class:`GameConfig` (everything the engine already configures).
* ``simulation`` -- run-time knobs (start time, steps, seconds-per-step, seed) that any
  world honors; these were previously only reachable as CLI flags on ``run_simulation``.
* ``retrieval`` -- the memory-retrieval scoring knobs (recency x relevance x importance
  weights, decay, how many memories to surface). These map onto
  :meth:`text_adventure_games.memory.AgentMemory.retrieve`'s parameters.
* ``cognition`` -- per-resident cognition defaults that used to be bare module
  constants: perception radius (vision, #80/#82) and conversation pacing (#86).
* ``embedding`` -- which embedding backend scores the *relevance* term, reusing the
  engine's :class:`~text_adventure_games.embedding_client.EmbeddingConfig`. ``None``
  (the default) means keyword-overlap relevance, the free offline path.

As with ``GameConfig``, **every field defaults to today's behavior**, so an empty
``SimulationConfig()`` (or passing none) changes nothing. Build it in Python, load it
from a YAML/JSON file (``from_file``), or read the environment (``from_env``), then hand
its pieces to the runner. See ``docs/design/simulation-config.md``.

Knobs for unbuilt phases stay **absent** rather than shipping as dead config: daily
planning (#83) and reflection (#84) are driven by the engine's ``GameConfig`` (e.g.
``agent.reflection_threshold``) and a live LLM client, and per-persona cognition
*overrides* land with their phase. A field appears here only once the sim actually
reads it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, is_dataclass

from text_adventure_games import memory as _memory
from text_adventure_games.config import GameConfig
from text_adventure_games.embedding_client import (
    EmbeddingClient,
    EmbeddingConfig,
    create_embedding_client,
)
from text_adventure_games.llm_client import LlmClient


@dataclass
class SimulationRuntimeConfig:
    """How long the sim runs and how its clock maps to in-game time.

    World-agnostic: any world honors these. They mirror ``run_simulation``'s original
    CLI flags (``--start`` / ``--steps`` / ``--sec-per-step``,
    made configurable in #74); the config gives them a declarative home so a scenario
    can ship them in a file.
    """

    start: str = "2023-02-13 08:00:00"  # in-game start, ISO 8601 (parsed by the runner)
    steps: int = 1080  # number of steps to simulate (1080 x 10s = 3 hours)
    sec_per_step: int = 10  # seconds of in-game time advanced per step
    seed: int | None = (
        None  # global RNG seed; carried for reproducibility, not yet used
    )


@dataclass
class RetrievalConfig:
    """Memory-retrieval scoring (``docs/design/agent-memory.md`` §6, issues #75/#76).

    Defaults equal the engine's ``memory.py`` module constants, so ``RetrievalConfig()``
    reproduces today's scoring exactly. Each field maps 1:1 onto a parameter of
    :meth:`text_adventure_games.memory.AgentMemory.retrieve`.
    """

    alpha_recency: float = _memory.ALPHA_RECENCY  # weight on the recency term (1.0)
    alpha_importance: float = _memory.ALPHA_IMPORTANCE  # weight on importance (1.0)
    alpha_relevance: float = _memory.ALPHA_RELEVANCE  # weight on relevance (1.0)
    recency_decay: float = _memory.DEFAULT_DECAY  # exponential decay per turn (0.95)
    max_records: int = _memory.DEFAULT_MAX_RECORDS  # max memories surfaced (6)
    token_budget: int = (
        _memory.DEFAULT_TOKEN_BUDGET
    )  # token ceiling for the block (800)


@dataclass
class CognitionConfig:
    """Per-resident cognition knobs for the features that landed after Phase A/B.

    These gather sim-level cognition defaults that used to be bare module constants
    in ``cognition.py``: how far a resident perceives (vision, issue #80/#82) and how
    the conversation pass is paced (#86). Defaults equal those constants, so
    ``CognitionConfig()`` reproduces today's behavior. A persona may still override its
    own ``vision_r`` per-entry in the world YAML; this is the global default.
    """

    vision_r: int = 8  # perception radius in tiles (cognition.DEFAULT_VISION_R)
    conversation_cooldown_steps: int = (
        90  # min steps between a given pair's conversations (CONVERSATION_COOLDOWN_STEPS)
    )
    conversation_max_exchanges: int = (
        6  # max back-and-forth lines per conversation (CONVERSATION_MAX_EXCHANGES)
    )


@dataclass
class SimulationConfig:
    """The one config object the sim hands to its runner.

    Compose it directly, load it from a file with :meth:`from_file`, or read the
    environment with :meth:`from_env`. Every field defaults to the sim's historical
    behavior, so an empty ``SimulationConfig()`` is a no-op.
    """

    game: GameConfig = field(default_factory=GameConfig)
    simulation: SimulationRuntimeConfig = field(default_factory=SimulationRuntimeConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    cognition: CognitionConfig = field(default_factory=CognitionConfig)
    embedding: EmbeddingConfig | None = None  # None -> keyword-overlap relevance

    @classmethod
    def from_file(cls, path) -> "SimulationConfig":
        """Load a config from a ``.yaml``/``.yml`` or ``.json`` file.

        Top-level keys are the section names (``game``, ``simulation``, ``retrieval``,
        ``cognition``, ``embedding``); the ``game`` section is itself a
        :class:`GameConfig` mapping (``engine``, ``observability``, ...). Any section you
        omit keeps its defaults.
        YAML needs ``pyyaml`` (ships with the engine); JSON needs nothing extra.
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
    def from_dict(cls, data: dict) -> "SimulationConfig":
        """Build a config from a plain dict (the shape :meth:`from_file` parses)."""
        unknown = set(data) - {
            "game",
            "simulation",
            "retrieval",
            "cognition",
            "embedding",
        }
        if unknown:
            raise ValueError(
                f"Unknown config section(s): {sorted(unknown)}. Valid sections: "
                "game, simulation, retrieval, cognition, embedding."
            )
        # The `game` section is a full GameConfig mapping -- delegate so its own
        # per-section validation (unknown engine/observability keys, etc.) applies.
        game_data = data.get("game")
        if game_data is not None:
            if not isinstance(game_data, dict):
                raise ValueError("Config section 'game' must be a mapping")
            game = GameConfig.from_dict(game_data)
        else:
            game = GameConfig()
        # The `embedding` section reuses the engine's EmbeddingConfig; absent -> None
        # (keyword relevance), mirroring how GameConfig treats its `llm` section.
        emb_data = data.get("embedding")
        if emb_data is not None:
            if not isinstance(emb_data, dict):
                raise ValueError("Config section 'embedding' must be a mapping")
            if "provider" not in emb_data:
                raise ValueError(
                    "The 'embedding' config section requires a 'provider' "
                    "(e.g. local, mock, openai, sentence-transformers)."
                )
            embedding = _build(EmbeddingConfig, emb_data, "embedding")
        else:
            embedding = None
        return cls(
            game=game,
            simulation=_build(
                SimulationRuntimeConfig, data.get("simulation", {}), "simulation"
            ),
            retrieval=_build(RetrievalConfig, data.get("retrieval", {}), "retrieval"),
            cognition=_build(CognitionConfig, data.get("cognition", {}), "cognition"),
            embedding=embedding,
        )

    @classmethod
    def from_env(cls) -> "SimulationConfig":
        """Build a config from environment variables.

        The ``game`` section reads the engine's ``LLM_*`` / ``OUTPUT_LEVEL`` /
        ``NO_COLOR`` / ``LLM_LOG`` vars (via :meth:`GameConfig.from_env`); the
        ``embedding`` section reads ``EMBEDDING_PROVIDER`` (plus ``EMBEDDING_MODEL`` /
        ``EMBEDDING_API_KEY`` / ``EMBEDDING_BASE_URL``), the same vars the engine's
        ``embedding_client_from_env`` honors. Run-time and retrieval knobs have no env
        vars (set them in a file or in Python); anything unset keeps its default.
        """
        config = cls()
        config.game = GameConfig.from_env()
        provider = os.environ.get("EMBEDDING_PROVIDER")
        if provider:
            config.embedding = EmbeddingConfig(
                provider=provider,
                model=os.environ.get("EMBEDDING_MODEL"),
                api_key=os.environ.get("EMBEDDING_API_KEY"),
                base_url=os.environ.get("EMBEDDING_BASE_URL"),
            )
        return config

    def to_dict(self) -> dict:
        """Serialize to a plain, JSON-able dict (inverse of :meth:`from_dict`)."""
        out = {
            "game": self.game.to_dict(),
            "simulation": _asdict(self.simulation),
            "retrieval": _asdict(self.retrieval),
            "cognition": _asdict(self.cognition),
        }
        if self.embedding is not None:
            emb = _asdict(self.embedding)
            # provider may be an EmbeddingProvider enum; store its plain string value.
            if emb.get("provider") is not None:
                emb["provider"] = str(emb["provider"])
            out["embedding"] = emb
        return out

    def build_embedding_client(self) -> EmbeddingClient | None:
        """Create an embedding client from :attr:`embedding`, or None if it isn't set.

        ``None`` keeps relevance on keyword overlap (the offline default). Mirrors
        :meth:`GameConfig.build_llm_client`; it does not swallow errors -- the runner
        wraps this to degrade to keyword relevance when a backend can't be created.
        """
        if self.embedding is None:
            return None
        return create_embedding_client(self.embedding)

    def build_llm_client(self) -> LlmClient | None:
        """Create an LLM client from the embedded :attr:`game` config, or None."""
        return self.game.build_llm_client()


def _build(dataclass_type, data, section_name):
    """Construct *dataclass_type* from *data*, rejecting unknown keys clearly.

    A local copy of the engine's ``config._build`` helper: the port reuses the engine's
    *public* API only, so we duplicate this tiny validator rather than import a private.
    """
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
    """Shallow dataclass -> dict (we only nest one level here, so this is enough)."""
    if not is_dataclass(obj):
        return obj
    return {f.name: getattr(obj, f.name) for f in fields(obj)}
