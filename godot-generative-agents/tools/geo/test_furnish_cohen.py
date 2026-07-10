# tools/geo/test_furnish_cohen.py
import json
import os

import furnish_cohen as fc

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMJ = os.path.join(
    REPO, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
)


def _tmj():
    return json.load(open(TMJ))


def test_cohen_sections_are_the_five_rooms():
    secs = fc.cohen_sections(_tmj())
    assert set(secs) == {
        "Kitchen 1",
        "Kitchen 2",
        "Cafeteria 1",
        "Cafeteria 2",
        "Cafeteria 3",
    }
    for rect in secs.values():
        c0, r0, c1, r1 = rect
        assert c0 <= c1 and r0 <= r1  # inclusive, well-formed


def test_kitchen_wall_cells_are_the_kitchen_cafeteria2_seam():
    tmj = _tmj()
    cells = fc.kitchen_wall_cells(tmj)
    assert cells, "expected a non-empty kitchen<->Cafeteria 2 seam"
    boxes = fc.cohen_boxes(tmj)
    kitchen = boxes["Kitchen 1"] | boxes["Kitchen 2"]
    caf2 = boxes["Cafeteria 2"]
    # every wall cell is a kitchen cell whose east neighbour is Cafeteria 2
    for x, y in cells:
        assert (x, y) in kitchen and (x + 1, y) in caf2
