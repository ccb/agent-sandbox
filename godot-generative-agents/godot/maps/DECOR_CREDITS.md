# Outdoor decoration tile art — credits & license

The plants scattered through the campus grass margins (small flowers, leaf tufts,
bushes and a mushroom — deliberately a different look from the Kenney campus trees)
are painted with the **Cute Fantasy** asset pack by **Kenmi**. The pack's
"Outdoor decoration" sheet is vendored here as:

| File in this repo  | Source sheet (Cute_Fantasy_Free)              |
| ------------------ | --------------------------------------------- |
| `decor_plants.png` | `Outdoor decoration/Outdoor_Decor_Free.png`   |

It is a byte-for-byte copy of the sheet already vendored under
`godot-generative-agents/Cute_Fantasy_Free/`, placed next to `upenn_core_urban.tmj`
so `tiled_map.gd` can load it as an extra tileset (the renderer reads each sheet
relative to the `.tmj`).

**Artist:** Kenmi — https://kenmi-art.itch.io/

**License (free version, from the pack's `read_me.txt`):** usable in non-commercial
projects; may be modified; **may not be redistributed or resold, even if modified.**
Included here only as a game asset for this research project.

The plants are stamped by `godot-generative-agents/tools/geo/frame_edges.py`, which registers this sheet as
a `.tmj` tileset and scatters a weighted mix of its single-tile plants through the
framed grass margin. See that script's header for the run order.
