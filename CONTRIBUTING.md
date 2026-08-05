# Contributing

Thanks for improving Penn Generative Agents. This public package favors changes
that keep the Penn showcase understandable, reproducible, and easy to fork.

## Start locally

```bash
git clone https://github.com/ccb/agent-sandbox.git
cd agent-sandbox
uv sync --extra dev --extra server
uv run pytest tests/ -q
uv run pytest godot-generative-agents/tests/ -q
```

Use Python 3.11–3.13. The committed `.python-version` and `uv.lock` provide the
recommended Python 3.12 environment. Copy `.env.example` to `.env` only if you
need a paid run; `.env` must remain untracked.

## Make a change

Create a focused branch and include tests for observable behavior. Prefer the
deterministic mock brain. A model should propose an action; the engine's
preconditions and effects must remain the authority.

Before opening a pull request, run the gates relevant to your change and ideally
the complete set documented in the root README. At minimum:

```bash
uv run black --check .
uv run pytest tests/ -q
uv run pytest godot-generative-agents/tests/ -q
```

Map changes also require the geo suite and drift validator. Godot changes require
`run_smoke_test.sh`. Web changes require `pnpm lint`, `pnpm test`, and
`pnpm build`. Public API documentation must build with MkDocs strict mode.

## Pull-request checklist

- Explain the user-visible outcome and the validation performed.
- Update docs and examples when commands, configuration, or extension points move.
- Do not include secrets, `.env`, raw prompts/responses, cassettes, `sim.db`,
  generated run directories, or unreviewed personal data.
- Check the license and attribution of new code, map data, fonts, sprites, and art.
- Avoid drive-by formatting or unrelated generated files.

If you are publishing a fork, also inspect its complete Git history: deleting a
secret or restricted asset from the latest tree does not remove it from history.
