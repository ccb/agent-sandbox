"""Run transcripts and provenance -- "save the whole run" (reproducible-runs, #197).

A cassette (see ``recording.py``) captures only the model's raw input/output. A
*transcript* captures the whole Observe -> Decide -> Act -> Reflect step and its
outcome: one :class:`StepRecord` per agent attempt.

A :class:`RunRecord` bundles a run's transcript with the *provenance* needed to
re-create it -- the game, the seed, the cassette (path + hash), the engine version
-- and saves it to a single human-readable YAML (or JSON) file. That is the unit
you commit next to a benchmark score so the number always comes with the recipe to
regenerate it.

Scope note (#197): this module ships the records and a :class:`TranscriptRecorder`
seam, but the ReAct loop does not populate it yet -- attaching ``game.transcript``
and calling :func:`record_step` from ``npc.py`` is a deferred follow-up. The
records here are useful on their own as the save-to-YAML provenance artifact.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# One step of the loop
# ---------------------------------------------------------------------------


@dataclass
class StepRecord:
    """One agent attempt: what it saw, what it said, and what happened.

    There is one of these per attempt, so a command that fails its precondition
    and is retried produces two records -- the failed one (``route_ok=False``,
    with a ``fail_reason``) and the retry.
    """

    turn: int
    actor: str
    observation: str
    system_prompt: str
    raw_response: str | None
    reasoning: str | None
    command: str | None
    route_ok: bool
    fail_reason: str | None
    world_delta: dict = field(default_factory=dict)

    def to_primitive(self) -> dict:
        return {
            "turn": self.turn,
            "actor": self.actor,
            "observation": self.observation,
            "system_prompt": self.system_prompt,
            "raw_response": self.raw_response,
            "reasoning": self.reasoning,
            "command": self.command,
            "route_ok": self.route_ok,
            "fail_reason": self.fail_reason,
            "world_delta": self.world_delta,
        }

    @classmethod
    def from_primitive(cls, data: dict) -> "StepRecord":
        return cls(
            turn=data["turn"],
            actor=data["actor"],
            observation=data["observation"],
            system_prompt=data["system_prompt"],
            raw_response=data.get("raw_response"),
            reasoning=data.get("reasoning"),
            command=data.get("command"),
            route_ok=data["route_ok"],
            fail_reason=data.get("fail_reason"),
            world_delta=data.get("world_delta") or {},
        )


class TranscriptRecorder:
    """Collects :class:`StepRecord`\\ s during a run.

    Attach one to a game before a run (``game.transcript = TranscriptRecorder()``)
    and, once the ReAct-loop hook is wired (a follow-up), it fills in; read
    ``recorder.steps`` afterward, or fold it into a :class:`RunRecord` to save.
    """

    def __init__(self):
        self.steps: list[StepRecord] = []

    def add_step(self, step: StepRecord) -> None:
        self.steps.append(step)


def record_step(game, **fields) -> None:
    """Append one :class:`StepRecord` to ``game.transcript`` if one is attached.

    A no-op when no recorder is attached, so a caller can invoke it
    unconditionally -- one line, no signature changes, zero cost when off.
    """
    recorder = getattr(game, "transcript", None)
    if recorder is None:
        return
    recorder.add_step(StepRecord(**fields))


# ---------------------------------------------------------------------------
# Provenance: the whole run, save-able to YAML
# ---------------------------------------------------------------------------


@dataclass
class RunRecord:
    """Everything needed to re-create and inspect one run.

    A run reproduces iff you can pin (game build + seed) + (cassette) + (code
    version). This bundles those with the step-by-step transcript and an optional
    scorer ``result``.
    """

    game: str
    seed: int
    cassette: dict = field(default_factory=dict)  # {"path": ..., "sha256": ...}
    engine_version: str = "unknown"  # git sha, best-effort
    steps: list[StepRecord] = field(default_factory=list)
    result: dict | None = None

    def to_primitive(self) -> dict:
        return {
            "game": self.game,
            "seed": self.seed,
            "cassette": self.cassette,
            "engine_version": self.engine_version,
            "result": self.result,
            "steps": [step.to_primitive() for step in self.steps],
        }

    @classmethod
    def from_primitive(cls, data: dict) -> "RunRecord":
        return cls(
            game=data["game"],
            seed=data["seed"],
            cassette=data.get("cassette") or {},
            engine_version=data.get("engine_version", "unknown"),
            steps=[StepRecord.from_primitive(s) for s in data.get("steps", [])],
            result=data.get("result"),
        )

    def save(self, path: str) -> None:
        """Write to *path*. ``.yaml``/``.yml`` -> YAML; ``.json`` -> JSON.

        YAML is the default, human-readable form a student can open and read.
        """
        data = self.to_primitive()
        with open(path, "w", encoding="utf-8") as f:
            if path.endswith((".yaml", ".yml")):
                yaml = _require_yaml()
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "RunRecord":
        with open(path, encoding="utf-8") as f:
            if path.endswith((".yaml", ".yml")):
                yaml = _require_yaml()
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        return cls.from_primitive(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def file_sha256(path: str) -> str:
    """Content hash of a file -- used to pin which cassette a run used."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha() -> str:
    """The current git commit (short sha), or ``"unknown"`` -- never raises.

    Provenance only: a missing or broken git checkout must not break a run.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _require_yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised only without pyyaml
        raise ImportError(
            "Saving/loading runs as YAML needs PyYAML. Install it with "
            "`pip install pyyaml` (or use a .json path instead)."
        ) from exc
    return yaml
