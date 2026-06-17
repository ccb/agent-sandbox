# Turn modes

The opt-in simultaneous turn mode — agents decide against a turn-start snapshot,
then commands resolve player-first and in initiative order.

::: text_adventure_games.turns
    options:
      heading_level: 2
      members:
        - Intent
        - gather_intents
        - phase_rank
        - resolve_order
        - run_simultaneous_round
