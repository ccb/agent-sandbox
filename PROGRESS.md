# Progress Tracker

## In flight (not yet on `main`)

Everything currently open — PRs and unclaimed issues — in one table, ordered by status.

| Status | Item | Title | Issue | Owner |
| --- | --- | --- | --- | --- |
| 🟢 Ready to merge | [#64](https://github.com/ccb/agent-sandbox/pull/64) | Adopt `uv` as the default project workflow | — | [@aking526](https://github.com/aking526) |
| 🟢 Ready to merge | [#52](https://github.com/ccb/agent-sandbox/pull/52) | Container / capacity inventory mechanics | [#43](https://github.com/ccb/agent-sandbox/issues/43) | [@MaEnqiMark](https://github.com/MaEnqiMark) |
| 🟠 Needs conflict resolution | [#61](https://github.com/ccb/agent-sandbox/pull/61) | Reproducible agent runs — record/replay, transcript, YAML run records | — | [@aking526](https://github.com/aking526) |
| 🟠 Needs conflict resolution | [#58](https://github.com/ccb/agent-sandbox/pull/58) | Goal-influencing dialogue (persuasion / negotiation) | [#46](https://github.com/ccb/agent-sandbox/issues/46) | [@MaEnqiMark](https://github.com/MaEnqiMark) |
| 🟠 Needs conflict resolution | [#57](https://github.com/ccb/agent-sandbox/pull/57) | Structured tool/function-calling interface for the LLM clients | [#44](https://github.com/ccb/agent-sandbox/issues/44) | [@MaEnqiMark](https://github.com/MaEnqiMark) |
| 🟠 Needs conflict resolution | [#54](https://github.com/ccb/agent-sandbox/pull/54) | Per-character knowledge / belief layer | [#45](https://github.com/ccb/agent-sandbox/issues/45) | [@aking526](https://github.com/aking526) |
| 🟠 Mergeability unverified | [#49](https://github.com/ccb/agent-sandbox/pull/49) | Contested resources + retry policy in simultaneous turn mode | [#42](https://github.com/ccb/agent-sandbox/issues/42) | [@aking526](https://github.com/aking526) |
| 🔵 In design (draft PR) | [#62](https://github.com/ccb/agent-sandbox/pull/62) | ScienceWorld benchmark interface | [#47](https://github.com/ccb/agent-sandbox/issues/47) | [@aking526](https://github.com/aking526) |
| 🔵 In design (draft PR) | [#59](https://github.com/ccb/agent-sandbox/pull/59) | Multi-step planning benchmark plan | [#47](https://github.com/ccb/agent-sandbox/issues/47) | [@aking526](https://github.com/aking526) |
| 🔵 In design (draft PR) | [#36](https://github.com/ccb/agent-sandbox/pull/36) | Generate a game from a Parsely-style PDF via LLM | [#29](https://github.com/ccb/agent-sandbox/issues/29) | [@0frankie](https://github.com/0frankie) |
| 🔵 In design (doc merged) | [`agent-memory.md`](docs/design/agent-memory.md) | Agent memory — approved design, Phase 2 | [#63](https://github.com/ccb/agent-sandbox/issues/63) | [@aking526](https://github.com/aking526) |
| 🔵 In design (doc merged) | [`llm-cost-observability.md`](docs/design/llm-cost-observability.md) | LLM cost / observability — long-term, not scheduled | — | [@aking526](https://github.com/aking526) |
| 🔵 In design (doc merged) | [`output-and-trace-rendering.md`](docs/design/output-and-trace-rendering.md) | Output & trace rendering — core landed, see §12 for remaining stages | — | [@aking526](https://github.com/aking526) |
| 💡 Backlog (no PR) | [#63](https://github.com/ccb/agent-sandbox/issues/63) | Prioritize & approve the agent memory layer (Phase 2) | — | [@aking526](https://github.com/aking526) |
| 💡 Backlog (no PR) | [#47](https://github.com/ccb/agent-sandbox/issues/47) | Multi-step planning benchmark | — | [@aking526](https://github.com/aking526) |
| 💡 Backlog (no PR) | [#41](https://github.com/ccb/agent-sandbox/issues/41) | Instantiate described-but-nonexistent objects from LLM room descriptions | — | [@0frankie](https://github.com/0frankie) |

---

## How to read & maintain this table

A single, at-a-glance view of where every feature, design doc, and PR stands across
`agent-sandbox`. This unifies what's otherwise scattered across GitHub issues, open PRs,
and the `docs/design/` folder.

For the *vision* see [`README.md`](README.md); for the *plan* see [`ROADMAP.md`](ROADMAP.md)
and [`FEATURE-ROADMAP.md`](FEATURE-ROADMAP.md). This file tracks *status* only.

**Status legend:**

| Status | Meaning |
| --- | --- |
| 🟢 Ready to merge | PR open, mergeable, not draft — awaiting review/merge |
| 🟠 Needs conflict resolution | PR open but conflicting with `main` (or mergeability unverified) |
| 🔵 In design | Design doc or draft PR; not yet implementing |
| 💡 Backlog | Open issue, no PR yet |
| ✅ Shipped | Merged to `main` — see the section below |

**Maintenance:** update the relevant row when a PR opens, lands, or stalls. When an item
merges, move it from the in-flight table to the Shipped section. Last synced with GitHub
on **2026-06-15**.

---

## ✅ Shipped (merged to `main`)

### Agent layer & ReAct loop
- [#2](https://github.com/ccb/agent-sandbox/issues/2) Mockable LLM client for offline testing — [#13](https://github.com/ccb/agent-sandbox/pull/13)
- [#3](https://github.com/ccb/agent-sandbox/issues/3) Promote NPCs to first-class Agents (decision seam) — [#14](https://github.com/ccb/agent-sandbox/pull/14)
- [#4](https://github.com/ccb/agent-sandbox/issues/4) Reflect step in the ReAct loop — [#17](https://github.com/ccb/agent-sandbox/pull/17)
- [#5](https://github.com/ccb/agent-sandbox/issues/5) Wire ReAct behavior into the live game end-to-end — [#21](https://github.com/ccb/agent-sandbox/pull/21)
- [#8](https://github.com/ccb/agent-sandbox/issues/8) Agent-to-agent interaction (actor seam + `say`) — [#19](https://github.com/ccb/agent-sandbox/pull/19)
- [#23](https://github.com/ccb/agent-sandbox/issues/23) First-class tiered goals — [#28](https://github.com/ccb/agent-sandbox/pull/28)
- Multi-agent demo notebook — [#20](https://github.com/ccb/agent-sandbox/pull/20)

### World model & engine
- [#1](https://github.com/ccb/agent-sandbox/issues/1) `Thing.get_property()` defaults to `False` — [#11](https://github.com/ccb/agent-sandbox/pull/11)
- [#6](https://github.com/ccb/agent-sandbox/issues/6) Event log + trigger system — [#16](https://github.com/ccb/agent-sandbox/pull/16)
- [#7](https://github.com/ccb/agent-sandbox/issues/7) Time model (turn clock, periods, scheduled events) — [#18](https://github.com/ccb/agent-sandbox/pull/18)
- [#22](https://github.com/ccb/agent-sandbox/issues/22) Gate NPC mechanics on world state, not narration — [#27](https://github.com/ccb/agent-sandbox/pull/27)
- [#24](https://github.com/ccb/agent-sandbox/issues/24) Per-turn NPC time budget / variable action durations — [#32](https://github.com/ccb/agent-sandbox/pull/32)
- [#25](https://github.com/ccb/agent-sandbox/issues/25) Opt-in simultaneous turn mode (gather/resolve) — [#30](https://github.com/ccb/agent-sandbox/pull/30)
- [#40](https://github.com/ccb/agent-sandbox/issues/40) Affordance tags + wear/wield slots — [#53](https://github.com/ccb/agent-sandbox/pull/53)
- Magic-string → enum refactor — [#48](https://github.com/ccb/agent-sandbox/pull/48)

### Testing, docs & tooling
- [#26](https://github.com/ccb/agent-sandbox/issues/26) Scenario-based integration tests — [#33](https://github.com/ccb/agent-sandbox/pull/33)
- [#38](https://github.com/ccb/agent-sandbox/issues/38) Fix coverage-hook interpreter resolution — [#39](https://github.com/ccb/agent-sandbox/pull/39)
- Project-shared Claude Code automations — [#34](https://github.com/ccb/agent-sandbox/pull/34)
- Local-only MkDocs documentation site — [#50](https://github.com/ccb/agent-sandbox/pull/50)
- Move `test_npc_behaviors.py` into `tests/` — [#51](https://github.com/ccb/agent-sandbox/pull/51)
- GitHub Actions CI running the `/check` gates — [#55](https://github.com/ccb/agent-sandbox/pull/55)

### Design docs merged
- Unified output & agent-trace rendering — [#31](https://github.com/ccb/agent-sandbox/pull/31)
- Simultaneous action resolution — [#35](https://github.com/ccb/agent-sandbox/pull/35)
- Agent memory — [#37](https://github.com/ccb/agent-sandbox/pull/37)
- LLM cost / observability — [#56](https://github.com/ccb/agent-sandbox/pull/56)

### Closed / deferred
- [#9](https://github.com/ccb/agent-sandbox/issues/9) Clean world-state export API for the Godot bridge — closed
- [#10](https://github.com/ccb/agent-sandbox/issues/10) Prototype Godot 2D renderer + websocket bridge — closed
