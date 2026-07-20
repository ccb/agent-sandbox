"""add_entrances FORCED_CLOSED -> entrance_floor repaint tests (#556)."""

import add_entrances as ae
import furnish_building as fb

W, H = 245, 279  # the real map dims; the helper only needs a correctly-sized list


def test_seal_forced_closed_floor_repaints_open_door_to_wall():
    # Every FORCED_CLOSED cell starts drawn as open door art (FLOOR)...
    floor = [0] * (W * H)
    for cells in ae.FORCED_CLOSED.values():
        for fx, fy in cells:
            floor[fy * W + fx] = ae.FLOOR
    ae.seal_forced_closed_floor(floor, W)
    # ...and ends repainted to WALL, matching its collision seal.
    for cells in ae.FORCED_CLOSED.values():
        for fx, fy in cells:
            assert floor[fy * W + fx] == ae.WALL


def test_seal_forced_closed_floor_touches_only_forced_closed_cells():
    floor = [ae.FLOOR] * (W * H)
    ae.seal_forced_closed_floor(floor, W)
    closed = {fy * W + fx for cells in ae.FORCED_CLOSED.values() for (fx, fy) in cells}
    assert all(floor[i] == ae.WALL for i in closed)
    sample = next(i for i in range(W * H) if i not in closed)
    assert floor[sample] == ae.FLOOR  # a non-closed cell is untouched


def test_williams_door_is_single_sourced():
    # One canonical value, no drift possible between the two modules.
    assert fb.SOUTH_DOOR_X == (43, 44)
    assert ae.WILLIAMS_DOOR_X == fb.SOUTH_DOOR_X
