# Penn Generative Agents web companion

This Vite/React application is the public project writeup and browser replay
viewer. It embeds reviewed static artifacts; it is not the authoritative
simulation engine.

## Develop

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Run the release gates:

```bash
pnpm lint
pnpm test
pnpm build
```

## Generated artifacts

Run these from this directory:

```bash
pnpm gen:replay     # Penn browser replay from retained source
pnpm gen:promptviz  # cognition graph from backend/promptviz_chains/cognition.yaml
pnpm gen:docs       # local MkDocs build copied into public/docs
pnpm export:godot   # web export of the Godot project
```

Review generated diffs before committing. `public/replay/penn_replay.json` is the
canonical showcased run and is intentionally tracked. Exported Godot and MkDocs
directories are build outputs and remain ignored.

The build uses the pinned `pnpm-lock.yaml` and Vite configuration. Keep replay
codec changes synchronized with Python's `backend/replay_codec.py` and cover both
implementations with tests.

## Publication safety

Do not place keys, raw model requests/responses, cassettes, databases, private run
directories, or personal data under `public/`. Verify the license and attribution
of every visual asset before deployment. The production deployment and clean
public-history process are managed separately from this source-tree snapshot.
