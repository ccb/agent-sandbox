"""Compatibility shim.

action_castle.py now lives in text_adventure_games/adventures/. This re-export
keeps the course's ``hw1_solution.action_castle`` import path working (the HW1
notebooks import from here). New code should import from
``text_adventure_games.adventures.action_castle`` directly.
"""

from text_adventure_games.adventures.action_castle import *  # noqa: F401,F403
