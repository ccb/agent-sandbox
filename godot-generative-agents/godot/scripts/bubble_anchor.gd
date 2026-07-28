extends RefCounted
## Pure bottom-anchor math for the viewer's floating bubbles (dialogue / wish /
## thinking, viewer.gd). Extracted so the anchoring invariant is unit-testable
## headlessly (tests/test_bubble_anchor.gd) without standing up the viewer scene.
## A Godot Label positions by its TOP-LEFT and auto-sizes height downward; to
## anchor the BOTTOM edge instead (so a taller bubble grows up, away from the
## sprite) we derive the top-left from the label's measured height.


## Top-left for a bubble of rendered `height` whose BOTTOM edge rests at
## `bottom_y`, horizontally centered across a `width`-wide box. Growing `height`
## moves the top up (more-negative y); `bottom_y` is invariant.
static func top_left(width: float, bottom_y: float, height: float) -> Vector2:
	return Vector2(-width / 2.0, bottom_y - height)
