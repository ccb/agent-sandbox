"""An optional in-game clock for the turn-based game loop (issue #7).

The engine already counts turns: ``Game.turn`` goes up by one every round
(see ``Game.end_turn``). This module adds an *optional* layer on top of that
counter which maps turns onto a more familiar notion of time:

* a **clock** — "the game starts at 8:00 AM and each turn takes 15 minutes,
  so on turn 3 it is 8:45 AM";
* **named periods** — coarse chunks of the day like "dawn", "morning",
  "afternoon", "dusk", and "night", useful for descriptions ("The churchyard
  is silent in the dusk light") and for NPC schedules ("the gravedigger only
  digs in the morning").

Design notes (see FEATURE-ROADMAP.md section 4 and
docs/design/multi-character-play.md section 6):

* **Time is opt-in.** A game without a clock behaves exactly as before: the
  turn counter still increments, but nothing is displayed and nothing else
  changes. You enable the clock by passing ``time_config`` to ``Game``.
* **One loop, one clock.** The ``GameClock`` never keeps its own state — it
  is a pure function of the turn number. Ask it "what time is it on turn N?"
  and it answers. This means there is exactly one source of time in the game
  (``Game.turn``) and the clock can never drift out of sync with it.

Example::

    from text_adventure_games import games

    game = games.Game(
        start_at,
        player,
        time_config={"start_hour": 8, "minutes_per_turn": 15},
    )
    game.clock.format_time(game.turn)   # '8:00 AM'
    game.clock.period_at(game.turn)     # 'morning'
"""

from __future__ import annotations

from .enums import Period

# Default day periods as (start_hour, name) pairs. Each period runs from its
# start hour up to the next period's start hour. The last period wraps around
# midnight: with these defaults "night" covers 20:00 through 4:59. Names use
# the Period enum but are stored alongside plain strings; since Period
# members ARE strings, custom periods can mix freely with the defaults.
DEFAULT_PERIODS = [
    (5, Period.DAWN),
    (8, Period.MORNING),
    (12, Period.AFTERNOON),
    (17, Period.DUSK),
    (20, Period.NIGHT),
]

MINUTES_PER_DAY = 24 * 60


class GameClock:
    """Maps the game's turn counter onto in-game time of day.

    The clock is stateless: every method takes a turn number and computes the
    answer from the configuration. ``Game`` owns the actual turn counter.

    Args:
        start_hour: hour of day (0-23) at turn 0. Defaults to 8 (8:00 AM).
        start_minute: minute (0-59) at turn 0. Defaults to 0.
        minutes_per_turn: how many in-game minutes pass each turn. Defaults
            to 15, so four turns make an hour.
        periods: list of ``(start_hour, name)`` pairs naming chunks of the
            day, or ``None`` for :data:`DEFAULT_PERIODS`. Pass an empty list
            to disable period names entirely.
    """

    def __init__(
        self,
        start_hour: int = 8,
        start_minute: int = 0,
        minutes_per_turn: int = 15,
        periods=None,
    ):
        if not 0 <= start_hour <= 23:
            raise ValueError(f"start_hour must be 0-23, got {start_hour}")
        if not 0 <= start_minute <= 59:
            raise ValueError(f"start_minute must be 0-59, got {start_minute}")
        if minutes_per_turn <= 0:
            raise ValueError(
                f"minutes_per_turn must be positive, got {minutes_per_turn}"
            )
        if periods is None:
            periods = DEFAULT_PERIODS
        for entry in periods:
            hour, name = entry
            if not 0 <= hour <= 23:
                raise ValueError(f"period start hour must be 0-23, got {hour}")
            if not name:
                raise ValueError("period names must be non-empty strings")

        self.start_hour = start_hour
        self.start_minute = start_minute
        self.minutes_per_turn = minutes_per_turn
        # Keep periods sorted by start hour so period_at can scan them in order.
        self.periods = sorted(periods, key=lambda entry: entry[0])

    def minutes_elapsed(self, turn: int) -> int:
        """Total in-game minutes that have passed after `turn` turns."""
        return turn * self.minutes_per_turn

    def time_at(self, turn: int):
        """The in-game time on a given turn, as a ``(day, hour, minute)`` tuple.

        ``day`` counts how many in-game midnights have passed (day 0 is the
        day the game starts on). ``hour`` is 0-23 and ``minute`` is 0-59.
        """
        total = self.start_hour * 60 + self.start_minute + self.minutes_elapsed(turn)
        day, minute_of_day = divmod(total, MINUTES_PER_DAY)
        hour, minute = divmod(minute_of_day, 60)
        return day, hour, minute

    def format_time(self, turn: int) -> str:
        """The in-game time on a given turn as a 12-hour string, e.g. '8:45 AM'."""
        _, hour, minute = self.time_at(turn)
        suffix = "AM" if hour < 12 else "PM"
        hour_12 = hour % 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{hour_12}:{minute:02d} {suffix}"

    def period_at(self, turn: int):
        """The name of the day period on a given turn, or None if no periods.

        A period runs from its start hour until the next period's start hour.
        Hours before the earliest start hour wrap around to the *last* period
        (e.g. 3 AM is still "night" with the default periods).
        """
        if not self.periods:
            return None
        _, hour, _ = self.time_at(turn)
        # The last period whose start hour is <= the current hour. If the
        # current hour comes before every start hour, we have wrapped past
        # midnight and are still in the previous day's final period.
        current = self.periods[-1][1]
        for start, name in self.periods:
            if start <= hour:
                current = name
        return current

    def describe(self, turn: int) -> str:
        """A human-readable time summary, e.g. '8:45 AM (morning)'."""
        time_str = self.format_time(turn)
        period = self.period_at(turn)
        if period:
            return f"{time_str} ({period})"
        return time_str

    # Serialization — mirrors the to/from_primitive pattern used by Thing
    # and Game. Note: only the configuration is saved; the current time is
    # always derived from Game.turn, which Game serializes itself.

    def to_primitive(self):
        """Serialize the clock's configuration to plain JSON-able data."""
        return {
            "start_hour": self.start_hour,
            "start_minute": self.start_minute,
            "minutes_per_turn": self.minutes_per_turn,
            "periods": [[hour, name] for hour, name in self.periods],
        }

    @classmethod
    def from_primitive(cls, data):
        """Rebuild a GameClock from `to_primitive` data."""
        return cls(
            start_hour=data["start_hour"],
            start_minute=data.get("start_minute", 0),
            minutes_per_turn=data["minutes_per_turn"],
            periods=[(hour, name) for hour, name in data["periods"]],
        )
