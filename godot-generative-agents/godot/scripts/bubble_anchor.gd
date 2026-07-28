extends RefCounted
## Bottom-anchor sizing + math for the viewer's floating bubbles (dialogue / wish /
## thinking, viewer.gd). Extracted so the anchoring invariant is unit-testable
## headlessly (tests/test_bubble_anchor.gd) without standing up the viewer scene.
## A Godot Label positions by its TOP-LEFT and auto-sizes height downward; to
## anchor the BOTTOM edge instead (so a taller bubble grows up, away from the
## sprite) we derive the top-left from the label's measured height.


## Shrink-wrap `label` to its current text and return the measured height. A Label
## outside a container only auto-GROWS its size to fit new text, never shrinks back
## (Godot clamps size UP to the minimum, not down) -- so its stylebox background
## would keep the tall box of a big bubble after it collapses to one short line.
## Snapping .size to the minimum makes the drawn box match the text every time, and
## also forces the wrapped height to recompute now (vs a stale .size.y that lags a
## frame after .text changes). Companion to top_left(): call this for the height,
## then top_left() for the position.
static func fit_to_text(label: Label) -> float:
	label.size = label.get_minimum_size()
	return label.size.y


## The box width for text of `text_len` characters: `min_w` up to `start_len`
## chars, then ramping linearly to `max_w` at `full_len` chars and clamped there.
## Longer text gets a wider box so it reflows into a shorter block instead of a
## tall column. Character count stands in for wrapped height on purpose -- Godot
## can't re-measure an autowrap Label's height across widths within one frame --
## so this stays pure and unit-testable headlessly.
static func width_for(text_len: int, min_w: float, max_w: float, start_len: int, full_len: int) -> float:
	if text_len <= start_len:
		return min_w
	if text_len >= full_len:
		return max_w
	var span := float(maxi(1, full_len - start_len))  # guard a misconfigured start >= full
	var t := float(text_len - start_len) / span
	return min_w + t * (max_w - min_w)


## Top-left for a bubble of rendered `height` whose BOTTOM edge rests at
## `bottom_y`, horizontally centered across a `width`-wide box. Growing `height`
## moves the top up (more-negative y); `bottom_y` is invariant.
static func top_left(width: float, bottom_y: float, height: float) -> Vector2:
	return Vector2(-width / 2.0, bottom_y - height)
