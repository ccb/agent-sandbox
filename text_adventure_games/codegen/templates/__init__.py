"""Per-template source emitters.

Each registered emitter takes (id, params) and returns a Python source string
for one Action or Block class. ``emit.py`` calls these in order and
concatenates their output into the final module.

Shared helpers live in ``_common`` (kept out of this package's __init__ to
avoid circular imports through the registry below).
"""

from ._common import python_class_name  # re-exported for convenience
from . import actions as action_templates
from . import blocks as block_templates

ACTION_EMITTERS = {
    "unlock_with_key": action_templates.emit_unlock_with_key,
    "read_inscription_to_banish": action_templates.emit_read_inscription_to_banish,
    "propose_marriage": action_templates.emit_propose_marriage,
    "wear_item": action_templates.emit_wear_item,
    "sit_on_furniture": action_templates.emit_sit_on_furniture,
    "npc_taunt": action_templates.emit_npc_taunt,
    "npc_kill": action_templates.emit_npc_kill,
    "flavor_response": action_templates.emit_flavor_response,
    "transform_item": action_templates.emit_transform_item,
}

BLOCK_EMITTERS = {
    "property_block": block_templates.emit_property_block,
    "darkness_block": block_templates.emit_darkness_block,
}
