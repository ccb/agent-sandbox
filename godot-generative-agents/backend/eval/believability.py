"""Believability audit over a finished run's exported artifacts (issue #584).

Live-run observability tells you what a run *cost*; nothing judges whether the
behavior was *sensible*. This tool reads the artifacts a run already exports --
movement frames with per-step act/reasoning/chat, each persona's memory stream,
the schedule in ``meta.personas`` -- and produces a per-agent day-coherence
report, so cognition changes (#579) can be compared run-over-run.

It is read-only and offline: point it at a baked replay JSON (what
``generate_penn_replay.py`` writes) or at a #304 RunStore run directory
(``runs/<run_id>/``). No live coupling, no new export fields.

Five rubric dimensions, each scored 1-10 with cited step examples:

* **plan coherence** -- did the agent's actions match its plan (or deviate
  visibly), in the plan's order?
* **temporal sanity** -- do activities land when the schedule says they
  should, without frame-to-frame thrash?
* **social grounding** -- do conversation lines reference real shared context
  (both participants' streams), between agents actually standing together?
* **world grounding** -- does the agent avoid claiming first-hand experience
  of (or inviting someone to) a place that doesn't exist in this world?
* **memory use** -- were the memories retrieved for a decision relevant to
  the action taken?

Two judges score the same evidence:

* :class:`HeuristicJudge` -- deterministic and free: transparent mechanical
  checks (word overlap, schedule windows, co-location). Always available; it
  is also the scrambled-control baseline the tests pin.
* :class:`LlmJudge` -- asks a real model to grade the rubric via one
  structured tool call per agent, billed to a
  :class:`~text_adventure_games.usage.UsageLedger` with a hard cost ceiling.
  Any malformed / declined reply falls back to the heuristic for that agent,
  so the tool always produces a full report (the mock provider exercises
  exactly this path offline).

Run from the repo root::

    uv run python -m backend.eval.believability godot-generative-agents/godot/maps/penn_replay.json
    uv run python -m backend.eval.believability godot-generative-agents/runs/<run_id> --out report.md

``--scramble frames`` (or ``plans``) grades a deliberately broken control --
shuffled frame order / swapped schedules -- which must score measurably worse
than the intact run (the issue's acceptance check).
"""

from __future__ import annotations

import argparse
import datetime
import json
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Loading: one dict, whichever artifact you point at
# ---------------------------------------------------------------------------


def load_replay(path: str | Path) -> dict:
    """Load run artifacts from *path* into the replay dict shape.

    Accepts either a baked replay JSON file (``{meta, frames, memory_streams,
    events}``, what ``generate_penn_replay.py`` writes) or a #304 RunStore run
    directory (``<runs-root>/<run_id>/`` with ``manifest.json`` beside
    ``frames.jsonl``); the run directory is assembled into the same dict via
    the #307 exporter, so everything downstream sees one shape.
    """
    path = Path(path)
    if path.is_dir():
        if not (path / "manifest.json").is_file():
            raise ValueError(
                f"{path} is a directory but has no manifest.json -- expected a "
                "RunStore run directory (runs/<run_id>/) or a replay JSON file"
            )
        # Imported here so reading a plain JSON file needs no store machinery.
        from backend.penn.export_replay import build_replay
        from backend.run_store import RunStore

        return build_replay(RunStore(path.parent), path.name)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# The scrambled control (acceptance: it must score measurably worse)
# ---------------------------------------------------------------------------

SCRAMBLE_MODES = ("frames", "plans")


def scramble_replay(replay: dict, mode: str, seed: int = 0) -> dict:
    """Return a deliberately broken copy of *replay* -- the audit's control.

    ``mode="frames"`` shuffles the frame order (a day chopped up and dealt
    out at random: acts no longer run in plan order or at sane times).
    ``mode="plans"`` rotates the schedules between agents (everyone spends
    the day executing somebody else's plan). The input is never mutated and
    the shuffle is seeded, so a control is reproducible.
    """
    if mode not in SCRAMBLE_MODES:
        raise ValueError(
            f"unknown scramble mode {mode!r}; choose from {SCRAMBLE_MODES}"
        )
    rng = random.Random(seed)
    out = dict(replay)
    if mode == "frames":
        frames = list(replay["frames"])
        rng.shuffle(frames)
        out["frames"] = frames
    else:  # plans
        personas = [dict(p) for p in replay["meta"].get("personas", [])]
        schedules = [p.get("schedule") for p in personas]
        # Rotate by one so every agent gets somebody ELSE's schedule.
        for persona, schedule in zip(personas, schedules[1:] + schedules[:1]):
            persona["schedule"] = schedule
        out["meta"] = dict(replay["meta"], personas=personas)
    return out


# ---------------------------------------------------------------------------
# Evidence: the digest of a run each judge reads
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A maximal stretch of consecutive steps with the same ``act`` text."""

    start: int
    end: int  # inclusive
    act: str

    @property
    def steps(self) -> int:
        return self.end - self.start + 1


@dataclass
class Conversation:
    """One chat window: who talked, when, and the transcript they shared."""

    start: int
    end: int  # inclusive
    participants: list[str]
    transcript: list  # [[speaker, line], ...]


@dataclass
class AgentEvidence:
    """Everything the judges read about one agent, digested from the replay."""

    name: str
    persona: str
    schedule: list[dict]  # [{place, activity, steps, ...}] from meta.personas
    plan_texts: list[str]  # the PLAN memories in the agent's stream
    memory_texts: list[str]  # every memory text in the agent's stream
    segments: list[Segment]
    conversations: list[Conversation]
    retrievals: list[dict]  # [{step, act, reasoning, memories}]
    positions: list[tuple[int, int]]  # (x, y) per step, for co-location
    n_steps: int
    vision_r: float
    start_dt: datetime.datetime | None
    sec_per_step: int
    world_places: list[str] = field(default_factory=list)  # meta.locations (#780)

    def time_at(self, step: int) -> str:
        """The sim wall-clock at *step* (``HH:MM``), or the bare step number
        when the replay carries no start time."""
        if self.start_dt is None:
            return f"step {step}"
        dt = self.start_dt + datetime.timedelta(seconds=step * self.sec_per_step)
        return f"{dt:%H:%M}"


def _parse_start(meta: dict) -> datetime.datetime | None:
    """The replay's sim start time ('2023-02-13 08:00:00'), or None."""
    raw = meta.get("start")
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def _segments_for(frames: list[dict], name: str) -> list[Segment]:
    """Collapse one agent's per-step ``act`` strings into segments."""
    segments: list[Segment] = []
    for step, frame in enumerate(frames):
        # .get like every other frame reader here: a frame missing an agent
        # (truncated bake, partial resume) reads as an empty act, not a crash.
        act = frame.get(name, {}).get("act", "")
        if segments and segments[-1].act == act:
            segments[-1].end = step
        else:
            segments.append(Segment(start=step, end=step, act=act))
    return segments


def _conversations_in(frames: list[dict]) -> list[Conversation]:
    """Find every chat window in the run.

    The bake paints the same transcript onto every participant's ``chat``
    for the frames the conversation spans, so a conversation is a maximal
    stretch of steps where the same transcript appears -- its participants
    are the agents carrying it.

    This leans on the viewer contract that a window's transcript is repainted
    *identically* frame to frame. A producer that instead accumulates lines
    per frame keys each growth as a new window here -- ``build_evidence``
    merges those growth windows back together right after calling this
    (:func:`_merge_growth_windows`, #799), so callers never see the
    fragmentation even though this function's own grouping stays
    identical-payload keying.
    """
    conversations: list[Conversation] = []
    open_convs: dict[str, Conversation] = {}  # transcript key -> in-progress window
    for step, frame in enumerate(frames):
        seen: dict[str, list[str]] = {}
        for name, entry in frame.items():
            chat = entry.get("chat")
            if chat:
                seen.setdefault(json.dumps(chat, ensure_ascii=False), []).append(name)
        # Extend windows still running this step; close the ones that stopped.
        for key in list(open_convs):
            if key in seen:
                conv = open_convs[key]
                conv.end = step
                conv.participants = sorted(set(conv.participants) | set(seen[key]))
            else:
                conversations.append(open_convs.pop(key))
        for key, names in seen.items():
            if key not in open_convs:
                open_convs[key] = Conversation(
                    start=step,
                    end=step,
                    participants=sorted(names),
                    transcript=json.loads(key),
                )
    conversations.extend(open_convs.values())
    conversations.sort(key=lambda c: c.start)
    return conversations


def _merge_growth_windows(conversations: list[Conversation]) -> list[Conversation]:
    """Collapse one live conversation's per-tick growth into a single window.

    ``_conversations_in`` groups frames by *identical* chat payload, and warns
    in its own docstring that a producer accumulating lines per frame "would
    key each growth as a new window and overcount". The multi-tick producer
    (#371) does exactly that -- one Dana/Casey meeting registered as 23
    windows -- which both fragments window context and would score the same
    line many times over.

    Starting no later than one step after the open window's end AND one
    transcript a prefix of the other means the same meeting growing
    tick-by-tick; the longer transcript wins. The prefix check matters: two
    windows that merely overlap in time but carry unrelated transcripts are a
    different conversation, not a growth, and must not be collapsed into one --
    doing so would silently discard whichever transcript lost, along with any
    confabulation inside it.

    "The open window" is tracked **per participant set**, not as the single last
    window appended. The producer keys its ``active`` map by pair frozenset, so
    two pairs can be talking at the same time; their growth fragments then
    interleave in ``(start, end)`` order, and comparing each one against the
    previous window overall would hand every A--B fragment a C--D window to fail
    the participants check against -- restoring the whole #799 overcount exactly
    when conversations overlap, which on a campus of fifteen is often. Keying by
    participants makes the old equality check redundant; the adjacency and prefix
    guards still keep a pair's genuinely *separate* later meeting apart, since it
    starts long after the earlier window's end.

    Called centrally from ``build_evidence``, right after ``_conversations_in``,
    so every dimension -- ``social_grounding``, ``world_grounding``, and the LLM
    judge's ``evidence_text`` -- reads the same merged ``AgentEvidence.conversations``
    (#799). It started out local to ``_world_grounding`` alone, deferred because
    fixing it centrally would move already-published ``social_grounding`` scores;
    that review has since happened.
    """
    merged: list[Conversation] = []
    open_window: dict[frozenset[str], Conversation] = {}
    for conv in sorted(conversations, key=lambda c: (c.start, c.end)):
        key = frozenset(conv.participants)
        prev = open_window.get(key)
        if prev is not None and conv.start <= prev.end + 1:
            short, long_ = sorted((conv.transcript, prev.transcript), key=len)
            if long_[: len(short)] == short:  # a growth of the open window
                prev.end = max(prev.end, conv.end)
                if len(conv.transcript) > len(prev.transcript):
                    prev.transcript = list(conv.transcript)
                continue
        window = Conversation(
            start=conv.start,
            end=conv.end,
            participants=list(conv.participants),
            transcript=list(conv.transcript),
        )
        merged.append(window)
        open_window[key] = window
    return merged


def build_evidence(replay: dict) -> dict[str, AgentEvidence]:
    """Digest *replay* into one :class:`AgentEvidence` per persona."""
    meta = replay.get("meta", {})
    frames = replay.get("frames", [])
    streams = replay.get("memory_streams", {})
    personas = meta.get("personas", [])
    start_dt = _parse_start(meta)
    sec_per_step = int(meta.get("sec_per_step", 10))
    vision_r = float(meta.get("vision_r", 8))
    conversations = _merge_growth_windows(_conversations_in(frames))
    world_places = sorted(meta.get("locations") or [])

    evidence: dict[str, AgentEvidence] = {}
    for spec in personas:
        name = spec["name"]
        stream = streams.get(name, [])
        retrievals = []
        positions = []
        for step, frame in enumerate(frames):
            entry = frame.get(name, {})
            positions.append((int(entry.get("x", 0)), int(entry.get("y", 0))))
            if entry.get("memories"):
                retrievals.append(
                    {
                        "step": step,
                        "act": entry.get("act", ""),
                        "reasoning": entry.get("reasoning"),
                        "memories": entry["memories"],
                    }
                )
        evidence[name] = AgentEvidence(
            name=name,
            persona=spec.get("persona", ""),
            schedule=spec.get("schedule", []),
            plan_texts=[m["text"] for m in stream if m.get("kind") == "plan"],
            memory_texts=[m["text"] for m in stream],
            segments=_segments_for(frames, name) if frames else [],
            conversations=[c for c in conversations if name in c.participants],
            retrievals=retrievals,
            positions=positions,
            n_steps=len(frames),
            vision_r=vision_r,
            start_dt=start_dt,
            sec_per_step=sec_per_step,
            world_places=world_places,
        )
    return evidence


# ---------------------------------------------------------------------------
# Scores and the rubric's five dimensions
# ---------------------------------------------------------------------------

# The rubric, in report order. Every judge scores exactly these.
DIMENSIONS = (
    "plan_coherence",
    "temporal_sanity",
    "social_grounding",
    "world_grounding",
    "memory_use",
)


@dataclass
class DimScore:
    """One rubric dimension for one agent: a 1-10 score (or None for "not
    applicable", e.g. social grounding when nobody talked), the cited step
    examples that justify it, and a short free-text note."""

    score: float | None
    evidence: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {"score": self.score, "evidence": self.evidence, "note": self.note}


def _scale(fraction: float) -> float:
    """Map a 0-1 quality fraction onto the rubric's 1-10 scale."""
    return round(1.0 + 9.0 * max(0.0, min(1.0, fraction)), 1)


# Words too common (or too mechanical) to count as shared context. "walking"
# and the address separators are in every travel act; the rest are glue words
# that would make any two texts look related.
_STOPWORDS = {
    "about",
    "and",
    "back",
    "best",
    "campus",
    "does",
    "for",
    "from",
    "going",
    "great",
    "have",
    "here",
    "into",
    "just",
    "like",
    "more",
    "over",
    "some",
    "spending",
    "that",
    "the",
    "their",
    "there",
    "they",
    "this",
    "time",
    "today",
    "walking",
    "with",
    "your",
}


# Common nouns for places a campus agent might invent (issue #780). Case is
# useless here: the real confabulations -- "boathouse", "the river", "athletic
# complex" -- were all lowercase. A hit is only a candidate: it is discarded
# when it falls inside a real location name, so "Kamin Gallery" and "Reception
# Hall" don't false-positive.
# ponytail: naive gazetteer; the LLM judge is the backstop when it misses.
_PLACE_NOUNS = frozenset(
    """annex arena bar boathouse bridge cafe center centre complex courtyard
    creek dorm field garden gallery gym lab market museum park pool quad rink
    restaurant river shop stadium station store studio theater theatre trail
    track""".split()
)

# Phrases that turn naming a place into a checkable claim: having been there,
# or inviting someone to go. Taken from the actual #780 transcript rather than
# invented. Bare mentions are allowed -- see the spec's non-goal.
_EXPERIENCE_CUES = (
    "been there",
    "check it out",
    "come by",
    "down there",
    "i went",
    "made it down",
    "make it down",
    "meet me",
    "minute walk",
    "shots of",
    "show me",
    "swing by",
    "totally went",
    "walk if you",
    "went to",
)


def _names_only_real_places(text: str, real: str, world_places: list[str]) -> bool:
    """Does this one line name a place that exists here, and none that doesn't?

    Cue matching in :meth:`HeuristicJudge._world_grounding` is window-scoped, so a
    partner's *allowed* off-map backstory makes every cue-carrying line in the
    window attributable -- including "meet me at the Cafe", where the Cafe is real
    (issue #807). A line that grounds itself is exempt.

    Two ways to name a real place, and both are needed. A gazetteer noun that
    resolves real covers "cafe"; a ``meta.locations`` name appearing verbatim
    covers "Van Pelt Library", which the common-noun gazetteer does not carry. The
    shipped Penn world matches exactly one gazetteer noun ("gallery", via Van Pelt
    -- Kamin Gallery), so the noun check alone would exempt almost nothing there.

    Returning False as soon as the line names *any* off-map noun is what keeps the
    corroborator catch: a line that names no place at all is not self-grounded, so
    it stays eligible to be scored.
    """
    low = text.lower()
    words = {word for word in re.findall(r"[a-z]+", low) if word in _PLACE_NOUNS}
    if any(word not in real for word in words):
        return False
    # Word boundaries, not a bare substring: a one-word world place ("Bar") would
    # otherwise match inside "barely". The place-noun check above can stay a plain
    # `in real` test because it compares whole words against the joined name list.
    return bool(words) or any(
        re.search(rf"\b{re.escape(place.lower())}\b", low) for place in world_places
    )


def _content_words(text: str) -> set[str]:
    """The meaningful lowercase words of *text* (4+ letters, minus stopwords).

    This tiny notion of "aboutness" is what every heuristic overlap check
    uses: two texts are related when they share at least one content word.
    """
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {w for w in words if len(w) >= 4 and w not in _STOPWORDS}


def _longest_nondecreasing(values: list[int]) -> int:
    """Length of the longest non-decreasing subsequence (repeat visits to the
    same stop are in order). O(n^2), fine for a day's worth of segments."""
    if not values:
        return 0
    best = [1] * len(values)
    for i in range(1, len(values)):
        for j in range(i):
            if values[j] <= values[i]:
                best[i] = max(best[i], best[j] + 1)
    return max(best)


# ---------------------------------------------------------------------------
# The deterministic heuristic judge
# ---------------------------------------------------------------------------


class HeuristicJudge:
    """Free, deterministic scoring: transparent mechanical checks.

    Each dimension reduces to simple, explainable fractions (word overlap
    with the schedule, schedule-window fit, co-location, retrieved-memory
    relevance) mapped onto 1-10. It is the always-available baseline: the
    LLM judge falls back to it per-agent, the mock provider exercises it
    offline, and the scrambled-control test pins that it can tell a real
    day from a shuffled one.
    """

    kind = "heuristic"

    def score_agent(
        self, ev: AgentEvidence, evidence_by_name: dict[str, AgentEvidence]
    ) -> dict[str, DimScore]:
        return {
            "plan_coherence": self._plan_coherence(ev),
            "temporal_sanity": self._temporal_sanity(ev),
            "social_grounding": self._social_grounding(ev, evidence_by_name),
            "world_grounding": self._world_grounding(ev),
            "memory_use": self._memory_use(ev),
        }

    # -- shared: which schedule stop does a segment's act text belong to? ----

    def _match_segments(self, ev: AgentEvidence) -> list[int | None]:
        """For each segment, the index of the schedule stop its act text best
        matches (shared content words with the stop's place + activity), or
        None when it matches no stop at all."""
        stop_words = [
            _content_words(f"{s.get('place', '')} {s.get('activity', '')}")
            for s in ev.schedule
        ]
        matches: list[int | None] = []
        for seg in ev.segments:
            act_words = _content_words(seg.act)
            overlaps = [len(act_words & words) for words in stop_words]
            best = max(overlaps, default=0)
            matches.append(overlaps.index(best) if best > 0 else None)
        return matches

    # -- dimension 1: plan coherence -----------------------------------------

    def _plan_coherence(self, ev: AgentEvidence) -> DimScore:
        """Did the agent do what its plan says, in the plan's order?

        *coverage*: the fraction of the day (step-weighted) spent in segments
        that match some schedule stop. *order*: of the matched segments, the
        fraction that appear in schedule order (longest non-decreasing run of
        stop indices). A shuffled day keeps coverage but destroys order; a
        swapped plan destroys coverage.
        """
        if not ev.segments or not ev.schedule:
            return DimScore(None, note="no schedule or no frames to compare")
        matches = self._match_segments(ev)
        total = sum(seg.steps for seg in ev.segments)
        on_plan = sum(
            seg.steps for seg, m in zip(ev.segments, matches) if m is not None
        )
        coverage = on_plan / total if total else 0.0
        matched_order = [m for m in matches if m is not None]
        order = (
            _longest_nondecreasing(matched_order) / len(matched_order)
            if matched_order
            else 0.0
        )
        evidence = []
        for seg, m in zip(ev.segments, matches):
            if m is not None and len(evidence) < 2:
                stop = ev.schedule[m]
                evidence.append(
                    f"steps {seg.start}-{seg.end} ({ev.time_at(seg.start)}): "
                    f"'{seg.act}' matches stop {m + 1} "
                    f"'{stop.get('activity', '')} at {stop.get('place', '')}'"
                )
        for seg, m in zip(ev.segments, matches):
            if m is None:
                evidence.append(
                    f"steps {seg.start}-{seg.end} ({ev.time_at(seg.start)}): "
                    f"'{seg.act}' matches no schedule stop"
                )
                break
        return DimScore(
            _scale(0.5 * coverage + 0.5 * order),
            evidence,
            f"{coverage:.0%} of the day on a planned stop; "
            f"{order:.0%} of matched segments in plan order",
        )

    # -- dimension 2: temporal sanity ----------------------------------------

    def _temporal_sanity(self, ev: AgentEvidence) -> DimScore:
        """Do activities happen at sane times, without thrashing?

        *stability*: a real day is a few long segments -- frame-to-frame act
        churn (many one-step segments) is the signature of a scrambled run.
        *window fit*: when the schedule budgets steps per stop, each matched
        segment's midpoint should land inside that stop's expected window
        (cumulative budgets, with generous slack for travel).
        """
        if not ev.segments:
            return DimScore(None, note="no frames to compare")
        n = ev.n_steps
        churn = (len(ev.segments) - 1) / max(1, n - 1)
        stability = max(0.0, 1.0 - 5.0 * churn)
        evidence = [
            f"{len(ev.segments)} activity stretches over {n} steps "
            f"(a coherent day changes activity rarely)"
        ]

        # Expected step window per stop: cumulative schedule budgets, with
        # slack for the unbudgeted walks between stops. A stop with steps=None
        # means "the rest of the day".
        windows: list[tuple[float, float]] = []
        cursor = 0.0
        budgeted = False
        for stop in ev.schedule:
            steps = stop.get("steps")
            if steps is None:
                windows.append((cursor, float(n)))
                cursor = float(n)
            else:
                budgeted = True
                windows.append((cursor, cursor + float(steps)))
                cursor += float(steps)
        slack = max(5.0, 0.2 * n)

        fit = None
        if budgeted and windows:
            matches = self._match_segments(ev)
            in_window = 0
            counted = 0
            for seg, m in zip(ev.segments, matches):
                if m is None or m >= len(windows):
                    continue
                lo, hi = windows[m]
                mid = (seg.start + seg.end) / 2
                counted += seg.steps
                if lo - slack <= mid <= hi + slack:
                    in_window += seg.steps
                elif len(evidence) < 3:
                    stop = ev.schedule[m]
                    evidence.append(
                        f"steps {seg.start}-{seg.end} ({ev.time_at(seg.start)}): "
                        f"'{seg.act}' happens far outside its scheduled window"
                    )
            fit = in_window / counted if counted else 0.0
            evidence.append(
                f"{fit:.0%} of planned activity falls inside its scheduled "
                f"time window"
            )
        fraction = stability if fit is None else 0.5 * stability + 0.5 * fit
        return DimScore(
            _scale(fraction),
            evidence,
            f"activity churn {churn:.0%}"
            + ("" if fit is None else f"; schedule-window fit {fit:.0%}"),
        )

    # -- dimension 3: social grounding ---------------------------------------

    def _social_grounding(
        self, ev: AgentEvidence, evidence_by_name: dict[str, AgentEvidence]
    ) -> DimScore:
        """Are conversations grounded in shared reality?

        Per conversation: were the participants actually standing together
        (within vision_r) while it played; does each speaker actually belong
        to it; and do its lines reference context found in BOTH participants'
        memory streams (not confabulation)?
        """
        if not ev.conversations:
            return DimScore(None, note="no conversations observed for this agent")
        scores = []
        evidence = []
        for conv in ev.conversations:
            others = [p for p in conv.participants if p in evidence_by_name]
            # Co-location: every pair within vision_r on each window step.
            together = 0
            span = range(conv.start, conv.end + 1)
            for step in span:
                pts = [
                    evidence_by_name[p].positions[step]
                    for p in others
                    if step < len(evidence_by_name[p].positions)
                ]
                if pts and all(
                    (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= ev.vision_r**2
                    for i, a in enumerate(pts)
                    for b in pts[i + 1 :]
                ):
                    together += 1
            coloc = together / len(span)

            # Speaker validity: every transcript line is spoken by a participant.
            lines = [line for line in conv.transcript if len(line) == 2]
            valid = (
                sum(1 for speaker, _ in lines if speaker in conv.participants)
                / len(lines)
                if lines
                else 0.0
            )

            # Grounding: a substantive line should share a content word with
            # every participant's memory stream (their plans + observations).
            stream_words = {
                p: _content_words(" ".join(evidence_by_name[p].memory_texts))
                for p in others
            }
            grounded = 0
            substantive = 0
            for speaker, text in lines:
                words = _content_words(text)
                if not words:
                    continue  # pure pleasantries carry no checkable claim
                substantive += 1
                if all(words & stream_words[p] for p in others):
                    grounded += 1
                elif len(evidence) < 3:
                    evidence.append(
                        f"steps {conv.start}-{conv.end}: line '{speaker}: {text}' "
                        f"references context absent from a participant's memories"
                    )
            grounding = grounded / substantive if substantive else 1.0

            scores.append(0.4 * coloc + 0.4 * grounding + 0.2 * valid)
            evidence.append(
                f"steps {conv.start}-{conv.end} ({ev.time_at(conv.start)}): "
                f"conversation between {', '.join(conv.participants)} -- "
                f"co-located {coloc:.0%} of the window, "
                f"{grounded}/{substantive} substantive lines grounded in both "
                f"streams"
            )
        return DimScore(
            _scale(sum(scores) / len(scores)),
            evidence,
            f"{len(ev.conversations)} conversation(s) checked",
        )

    # -- dimension 4: world grounding -----------------------------------------

    def _world_grounding(self, ev: AgentEvidence) -> DimScore:
        """Does the agent talk about places that actually exist (issue #780)?

        Naming an off-map place is allowed -- a rower may talk about her
        boathouse. What is not allowed is claiming first-hand experience of it
        or inviting someone to meet there, so only cue-carrying lines score.

        Cues are matched **per window, not per line**: the worst line in the
        run that motivated this ("Oh yeah, I totally went! The light was
        perfect down there") names no place at all, and is only attributable
        because the partner named the boathouse earlier in the same window.

        Window scoping costs precision, so a line that names a real place and no
        off-map one is exempt (#807): "meet me at the Cafe" is not a claim about
        my partner's boathouse just because she mentioned it in the same window.
        """
        if not ev.conversations:
            return DimScore(None, note="no conversations observed for this agent")
        if not ev.world_places:
            return DimScore(
                None, note="replay carries no meta.locations (baked before #780)"
            )
        real = " | ".join(ev.world_places).lower()
        scores: list[float] = []
        evidence: list[str] = []
        for conv in ev.conversations:
            lines = [line for line in conv.transcript if len(line) == 2]
            # Every place-noun word this window names at all, and which of
            # those are off-map. Tracking *both* (not just the off-map ones)
            # is what lets the evidence say what the classifier saw: "cafe,
            # gym -- all real" reads differently from "saw nothing", even
            # though both currently score 10.0 -- and a real Penn world where
            # "Franklin Field" kills "field" or "Pottruck Gym" kills "gym" (the
            # substring check is deliberate, see module docstring) needs that
            # distinction visible, or a blinded gazetteer is invisible too.
            seen = sorted(
                {
                    word
                    for _, text in lines
                    for word in re.findall(r"[a-z]+", text.lower())
                    if word in _PLACE_NOUNS
                }
            )
            invented = [word for word in seen if word not in real]
            mine = [(sp, tx) for sp, tx in lines if sp == ev.name]
            if not mine:
                continue
            claimed = [
                (sp, tx)
                for sp, tx in mine
                if invented
                and any(cue in tx.lower() for cue in _EXPERIENCE_CUES)
                and not _names_only_real_places(tx, real, ev.world_places)
            ]
            scores.append(1.0 - len(claimed) / len(mine))
            for sp, tx in claimed[:3]:
                # Name the cue phrase(s) that turned this line into a claim:
                # it is real signal, and it makes two claims in one window read
                # distinctly instead of emitting the same string twice. Cues
                # are a fixed vocabulary with no place nouns in it, so quoting
                # them cannot smuggle a raw place name back into the evidence
                # and mask a place-classification assertion (see #780 I2).
                cues = ", ".join(c for c in _EXPERIENCE_CUES if c in tx.lower())
                evidence.append(
                    f"steps {conv.start}-{conv.end} ({ev.time_at(conv.start)}): "
                    f'{sp} claims first-hand experience ("{cues}") in a window '
                    f"that names {', '.join(invented)} -- not in this world"
                )
            if invented and not claimed:
                evidence.append(
                    f"steps {conv.start}-{conv.end}: mentions {', '.join(invented)} "
                    f"(not in this world) without claiming to have been there -- "
                    f"allowed, not scored"
                )
            elif not claimed:
                # No claim was flagged here -- but say what the classifier
                # actually saw, so a gazetteer that silently missed everything
                # doesn't read the same as a genuinely clean day. (When a claim
                # WAS flagged, the per-line findings above already name what was
                # seen, so this summary would only repeat them.) Reaching this
                # branch means `invented` is empty -- a non-empty `invented`
                # with no claim took the branch above -- so the verdict is just
                # "nothing" vs "all real".
                verdict = (
                    f"place words seen: {', '.join(seen)} -- all real"
                    if seen
                    else "no place words seen"
                )
                evidence.append(
                    f"steps {conv.start}-{conv.end} ({ev.time_at(conv.start)}): "
                    f"{verdict}; {len(mine)} line(s) of {ev.name} checked"
                )
        if not scores:
            return DimScore(None, note="this agent said nothing in any window")
        return DimScore(
            _scale(sum(scores) / len(scores)),
            evidence,
            f"{len(scores)} conversation window(s) checked against "
            f"{len(ev.world_places)} real place(s)",
        )

    # -- dimension 5: memory use ----------------------------------------------

    def _memory_use(self, ev: AgentEvidence) -> DimScore:
        """Were the memories retrieved for each decision relevant to it?

        A decision frame carries the memories retrieval surfaced for it; a
        relevant retrieval shares a content word with the action taken (or
        the reasoning given for it).
        """
        if not ev.retrievals:
            return DimScore(None, note="no decision frames carry retrieved memories")
        relevant = 0
        evidence = []
        for r in ev.retrievals:
            decision_words = _content_words(f"{r['act']} {r.get('reasoning') or ''}")
            hit = None
            for mem in r["memories"]:
                if _content_words(mem.get("text", "")) & decision_words:
                    hit = mem
                    break
            if hit is not None:
                relevant += 1
                if len(evidence) < 2:
                    evidence.append(
                        f"step {r['step']} ({ev.time_at(r['step'])}): retrieved "
                        f"'{hit['text']}' while '{r['act']}'"
                    )
            elif len(evidence) < 3:
                evidence.append(
                    f"step {r['step']} ({ev.time_at(r['step'])}): none of the "
                    f"{len(r['memories'])} retrieved memories relate to "
                    f"'{r['act']}'"
                )
        fraction = relevant / len(ev.retrievals)
        return DimScore(
            _scale(fraction),
            evidence,
            f"{relevant}/{len(ev.retrievals)} decisions used a relevant memory",
        )


# ---------------------------------------------------------------------------
# The audit: judge every agent, roll up a run summary
# ---------------------------------------------------------------------------


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def audit(
    replay: dict, judge=None, source: str = "", scramble: str | None = None
) -> dict:
    """Score every agent in *replay* with *judge* and return the report dict.

    The report has per-agent sections (each dimension's score + cited step
    examples) and a run-level summary (per-dimension and overall means over
    the agents that could be scored). ``judge`` defaults to the free
    :class:`HeuristicJudge`; pass an :class:`LlmJudge` for model grading.
    """
    if judge is None:
        judge = HeuristicJudge()
    evidence = build_evidence(replay)
    agents: dict[str, dict] = {}
    for name, ev in evidence.items():
        dims = judge.score_agent(ev, evidence)
        scores = [d.score for d in dims.values() if d.score is not None]
        agents[name] = {
            "dimensions": {dim: dims[dim].to_dict() for dim in DIMENSIONS},
            "overall": _mean(scores),
        }
    by_dimension = {
        dim: _mean(
            [
                a["dimensions"][dim]["score"]
                for a in agents.values()
                if a["dimensions"][dim]["score"] is not None
            ]
        )
        for dim in DIMENSIONS
    }
    overall = _mean([a["overall"] for a in agents.values() if a["overall"] is not None])
    return {
        "run": {
            "source": source,
            "steps": len(replay.get("frames", [])),
            "personas": len(evidence),
            "scramble": scramble,
        },
        "judge": judge_info(judge),
        "agents": agents,
        "summary": {"overall": overall, "by_dimension": by_dimension},
    }


def judge_info(judge) -> dict:
    """The report's judge/spend block; the LLM judge overrides this."""
    info = getattr(judge, "info", None)
    if callable(info):
        return info()
    return {"kind": getattr(judge, "kind", "heuristic")}


# ---------------------------------------------------------------------------
# The LLM judge (issue #584): one structured tool call per agent
# ---------------------------------------------------------------------------

# One rubric dimension, as the model must return it.
_DIM_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "1 (broken) to 10 (believable)."},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Step-cited examples, e.g. 'steps 120-180: ...'.",
        },
        "note": {"type": "string", "description": "A one-line verdict."},
    },
    "required": ["score", "evidence"],
}

# Normalized {name, description, parameters} -- the shape llm_client.call_tool
# translates per provider, like cognition's IMPORTANCE_SCORE_TOOL.
BELIEVABILITY_TOOL = {
    "name": "grade_believability",
    "description": (
        "Grade one agent's recorded day on the five believability dimensions, "
        "1-10 each, with step-cited evidence."
    ),
    "parameters": {
        "type": "object",
        "properties": {dim: _DIM_SCHEMA for dim in DIMENSIONS},
        "required": list(DIMENSIONS),
    },
}

# Caps on the evidence digest, so a scrambled (or simply long) run cannot blow
# the judge's context window: a shuffled 1200-step day has ~1000 one-step
# segments, and the middle of that list says nothing the ends don't.
_MAX_TIMELINE_LINES = 60
_MAX_CONVERSATIONS = 10
_MAX_RETRIEVALS = 8
_MAX_MEMORIES_PER_RETRIEVAL = 3


def _elide(lines: list[str], cap: int) -> list[str]:
    """Keep the first and last half of *lines* when there are more than *cap*."""
    if len(lines) <= cap:
        return lines
    half = cap // 2
    omitted = len(lines) - 2 * half
    return lines[:half] + [f"... {omitted} more entries omitted ..."] + lines[-half:]


def evidence_text(ev: AgentEvidence, evidence_by_name: dict[str, AgentEvidence]) -> str:
    """The per-agent digest the LLM judge reads: everything relevant from the
    run's artifacts, preformatted and capped. The rubric wording itself lives
    in ``prompt_templates/believability_rubric.prompty``; this is the
    ``evidence`` variable it renders."""
    lines = [f"Agent: {ev.name}"]
    if ev.persona:
        lines.append(f"Persona: {ev.persona}")
    if ev.start_dt is not None:
        lines.append(
            f"Sim day starts {ev.start_dt}; one step is {ev.sec_per_step}s; "
            f"{ev.n_steps} steps recorded."
        )
    if ev.world_places:
        lines.append(
            "Places that exist in this world: " + ", ".join(ev.world_places) + "."
        )

    lines += ["", "Schedule (the plan the day was generated from):"]
    for i, stop in enumerate(ev.schedule, start=1):
        steps = stop.get("steps")
        budget = f"{steps} steps" if steps is not None else "rest of the day"
        lines.append(
            f"{i}. {stop.get('place', '?')} -- {stop.get('activity', '?')} ({budget})"
        )

    if ev.plan_texts:
        lines += ["", "Plan memories in the agent's stream:"]
        lines += [f"- {text}" for text in ev.plan_texts]

    lines += ["", "Timeline (consecutive same-activity steps collapsed):"]
    timeline = [
        f"steps {seg.start}-{seg.end} ({ev.time_at(seg.start)}): {seg.act}"
        for seg in ev.segments
    ]
    lines += _elide(timeline, _MAX_TIMELINE_LINES)

    if ev.conversations:
        lines += ["", "Conversations this agent took part in:"]
        for conv in ev.conversations[:_MAX_CONVERSATIONS]:
            lines.append(
                f"steps {conv.start}-{conv.end} ({ev.time_at(conv.start)}), "
                f"between {', '.join(conv.participants)}:"
            )
            for speaker, text in conv.transcript:
                lines.append(f"  {speaker}: {text}")

    if ev.retrievals:
        lines += ["", "Decisions and the memories retrieved for them:"]
        for r in _elide(ev.retrievals, _MAX_RETRIEVALS):
            if isinstance(r, str):  # the elision marker
                lines.append(r)
                continue
            lines.append(
                f"step {r['step']} ({ev.time_at(r['step'])}): doing '{r['act']}'"
                + (f" -- reasoning: {r['reasoning']}" if r.get("reasoning") else "")
            )
            for mem in r["memories"][:_MAX_MEMORIES_PER_RETRIEVAL]:
                lines.append(
                    f"  retrieved [{mem.get('kind', '?')}]: {mem.get('text', '')}"
                )

    # What the other agents' memory streams say, so the judge can check that
    # dialogue references SHARED context (both sides), not one-sided invention.
    partners = sorted(
        {p for conv in ev.conversations for p in conv.participants if p != ev.name}
    )
    for partner in partners[:_MAX_CONVERSATIONS]:
        other = evidence_by_name.get(partner)
        if other is None or not other.memory_texts:
            continue
        lines += ["", f"{partner}'s memory stream (their side of the shared context):"]
        lines += _elide(
            [f"- {t}" for t in other.memory_texts], _MAX_TIMELINE_LINES // 2
        )

    return "\n".join(lines)


class LlmJudge:
    """Grade the rubric with a real model, one tool call per agent.

    Spend goes through the client's :class:`UsageLedger`; arm
    ``client.ledger.max_cost_usd`` and the judge stops calling the moment the
    ceiling is hit (acceptance c). Whenever the model declines, replies
    malformed, or the budget is gone, the deterministic
    :class:`HeuristicJudge` fills in -- so a report always completes, and the
    free mock provider (which declines every tool call) exercises exactly
    this fallback offline.
    """

    kind = "llm"

    def __init__(self, client, max_tokens: int = 1024):
        self.client = client
        self.max_tokens = max_tokens
        self.heuristic = HeuristicJudge()

    def score_agent(
        self, ev: AgentEvidence, evidence_by_name: dict[str, AgentEvidence]
    ) -> dict[str, DimScore]:
        fallback = self.heuristic.score_agent(ev, evidence_by_name)
        ledger = getattr(self.client, "ledger", None)
        if ledger is not None and ledger.over_budget():
            return self._noted(fallback, "judge budget exhausted; heuristic score")

        # Attribute the call to this agent in the ledger (usage.py context).
        ctx = getattr(self.client, "context", None)
        if ctx is not None:
            ctx.update({"actor": ev.name, "turn": 0, "attempt": 0, "role": "judge"})
        from backend.prompt_templates import render

        messages = [
            {
                "role": "user",
                "content": render(
                    "believability_rubric",
                    evidence=evidence_text(ev, evidence_by_name),
                ),
            }
        ]
        reply = self.client.call_tool(
            messages, BELIEVABILITY_TOOL, max_tokens=self.max_tokens
        )
        if not isinstance(reply, dict):
            return self._noted(
                fallback, "model declined or replied malformed; heuristic score"
            )

        scores: dict[str, DimScore] = {}
        for dim in DIMENSIONS:
            entry = reply.get(dim)
            raw = entry.get("score") if isinstance(entry, dict) else None
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                # This dimension came back unusable; keep the heuristic's.
                d = fallback[dim]
                scores[dim] = DimScore(
                    d.score,
                    d.evidence,
                    "model reply malformed for this dimension; heuristic score",
                )
                continue
            evidence = entry.get("evidence")
            scores[dim] = DimScore(
                score=max(1.0, min(float(raw), 10.0)),
                evidence=(
                    [str(e) for e in evidence] if isinstance(evidence, list) else []
                ),
                note=str(entry.get("note", "")),
            )
        return scores

    @staticmethod
    def _noted(scores: dict[str, DimScore], note: str) -> dict[str, DimScore]:
        """The heuristic's scores, re-labelled with why the model didn't grade."""
        return {
            dim: DimScore(d.score, d.evidence, f"{note} ({d.note})" if d.note else note)
            for dim, d in scores.items()
        }

    def info(self) -> dict:
        """The report's judge/spend block, read straight from the ledger."""
        ledger = getattr(self.client, "ledger", None)
        config = getattr(self.client, "config", None)
        provider = getattr(config, "provider", None)
        model = getattr(config, "model", None)
        # Some clients (the mock) carry no config; the ledger's call records
        # still know who was billed.
        if provider is None and ledger is not None and ledger.records:
            provider = ledger.records[0].usage.provider
            model = model or ledger.records[0].usage.model
        return {
            "kind": self.kind,
            "provider": provider,
            "model": model,
            "calls": len(ledger.records) if ledger is not None else 0,
            "cost_usd": (
                round(ledger.total_cost_usd(), 6) if ledger is not None else 0.0
            ),
            "max_cost_usd": getattr(ledger, "max_cost_usd", None),
        }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _label(dim: str) -> str:
    return dim.replace("_", " ").capitalize()


def _fmt_score(score: float | None) -> str:
    return "n/a" if score is None else f"{score:g}/10"


def render_markdown(report: dict) -> str:
    """The report as one readable markdown document."""
    run = report["run"]
    judge = report["judge"]
    lines = [
        "# Believability audit",
        "",
        f"- Run: `{run['source']}` -- {run['steps']} steps, "
        f"{run['personas']} personas"
        + (f", **scrambled control ({run['scramble']})**" if run["scramble"] else ""),
        f"- Judge: {judge['kind']}"
        + (
            f" ({judge.get('provider')}/{judge.get('model')}), "
            f"{judge.get('calls', 0)} calls, ${judge.get('cost_usd', 0.0):.4f} spent"
            f" (ceiling ${judge.get('max_cost_usd'):.2f})"
            if judge["kind"] == "llm" and judge.get("max_cost_usd") is not None
            else ""
        ),
        "",
        "## Run summary",
        "",
        "| Dimension | Mean score |",
        "| --- | --- |",
    ]
    for dim in DIMENSIONS:
        lines.append(
            f"| {_label(dim)} | {_fmt_score(report['summary']['by_dimension'][dim])} |"
        )
    lines.append(f"| **Overall** | **{_fmt_score(report['summary']['overall'])}** |")
    for name, agent in report["agents"].items():
        lines += ["", f"## {name}", "", f"Overall: **{_fmt_score(agent['overall'])}**"]
        for dim in DIMENSIONS:
            entry = agent["dimensions"][dim]
            lines += ["", f"### {_label(dim)}: {_fmt_score(entry['score'])}"]
            if entry["note"]:
                lines.append(f"_{entry['note']}_")
            for example in entry["evidence"]:
                lines.append(f"- {example}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_MAX_COST_USD = 1.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Believability audit over a finished run's artifacts (#584). "
        "Reads a baked replay JSON or a RunStore run directory; writes a "
        "per-agent day-coherence report."
    )
    ap.add_argument(
        "path",
        help="a baked replay JSON (e.g. godot/maps/penn_replay.json) or a "
        "RunStore run directory (runs/<run_id>/)",
    )
    ap.add_argument(
        "--out", default=None, help="write the report here (default: stdout)"
    )
    ap.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="report format (default: markdown)",
    )
    ap.add_argument(
        "--scramble",
        choices=SCRAMBLE_MODES,
        default=None,
        help="audit a deliberately broken control instead: shuffled frame "
        "order or swapped schedules (the acceptance comparison)",
    )
    ap.add_argument(
        "--seed", type=int, default=0, help="seed for --scramble (default: 0)"
    )
    ap.add_argument(
        "--max-cost-usd",
        type=float,
        default=DEFAULT_MAX_COST_USD,
        help="hard ceiling on judge spend, enforced through the usage ledger "
        f"(default: ${DEFAULT_MAX_COST_USD:.2f})",
    )
    ap.add_argument(
        "--no-llm",
        action="store_true",
        help="skip the model judge entirely and use the free heuristic",
    )
    args = ap.parse_args(argv)

    replay = load_replay(args.path)
    if args.scramble:
        replay = scramble_replay(replay, args.scramble, seed=args.seed)

    # Judge selection: LLM_PROVIDER (anthropic / openai / mock) via the shared
    # client factory, spend capped through its ledger; no provider (or
    # --no-llm) means the free deterministic heuristic.
    judge = None
    if not args.no_llm:
        from text_adventure_games.llm_client import client_from_env

        client = client_from_env()
        if client is not None:
            client.ledger.max_cost_usd = args.max_cost_usd
            judge = LlmJudge(client)
    if judge is None:
        # Informational only, and on stderr: stdout carries nothing but the
        # report itself, so `--format json | jq` always parses.
        print(
            "No LLM judge (set LLM_PROVIDER to enable one); using the heuristic.",
            file=sys.stderr,
        )

    report = audit(replay, judge=judge, source=str(args.path), scramble=args.scramble)
    text = (
        json.dumps(report, indent=2, ensure_ascii=False)
        if args.format == "json"
        else render_markdown(report)
    )
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
