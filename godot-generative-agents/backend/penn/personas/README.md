# The Penn persona library (#731)

One file per persona. A world YAML names its cast by reference —
`cast: [diego, tanaka, sofia]` in `../world_data_upenn.yaml` — and the loader
(`backend.build_world.load_world_yaml`) composes the run's `personas`,
`relationships`, and `meetings` from these files at build time. Add an id to
the `cast:` list (or pass a `cast=` override to `build_penn_world`) to put a
persona in the run; nothing here runs unless a cast names it.

## Catalog

| id | persona | in default cast? |
|----|---------|------------------|
| `diego` | Diego Torres, architecture grad student | yes |
| `tanaka` | Professor Tanaka, physicist | yes |
| `sofia` | Sofia Ramirez, first-year | yes |
| `maya` | Maya Chen, biology sophomore | no (parked for the 3-agent live-LLM MVP) |
| `priya` | Priya Nair, CS junior | no |
| `ellis` | Professor Ellis, historian | no |
| `marcus` | Marcus Webb, campus tour guide | no |

## File format

Persona fields (same shape `build_world` has always consumed): `name`, `home`,
`persona`, `emoji`, `start_tile`, `schedule` (see the big comment atop
`backend/build_world.py` for the schedule contract, and note a stop's `place`
must not contain a bare compass word — the parser reads "West Wing" as "go
west"). Plus two optional blocks that compose into the world's top level:

- `relationships:` — seed social-graph edges (`{a, b, kind, closeness,
  description}`; `closeness` is 1 (acquaintance) to 5 (inseparable) and drives
  edge thickness in the viewer's social-graph pop-up, #252). `description`
  stays natural language so a future pass (#409) can seed it into agent memory.
- `meetings:` — scripted encounters (`{label, at, participants, dialogue}`)
  the replay/live conversation injectors play when the participants are
  actually co-located (proximity-honest: if they never converge in a given
  run, the meeting is skipped with a warning, never faked). `at` must name a
  location in the world YAML; each `dialogue` line is `[speaker, text]` and
  the speaker must be a participant. Keep exchanges short: the viewer plays
  ~14 steps per line, and the whole exchange must fit inside the window the
  participants are actually together.

## Ownership + composition rules

- An edge or meeting lives in the file of its **first-named** persona (`a:` /
  `participants[0]`) — one home per entry, no duplication.
- Composition follows **cast order**, and cast order is persona order in the
  replay — reordering the default cast changes the baked bytes (#640 guards
  this).
- Entries referencing someone outside the cast are **dropped at load time**:
  an edge needs both ends in the cast, a meeting needs all its participants.
  So casting `maya` without `priya` simply loses their shared edge/meeting —
  no error, no dangling reference.
