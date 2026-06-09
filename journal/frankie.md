## 2026-06-08
**Focus:** working on issue #23 and looking into logging for triggers

**Done today:**
- finished rebasing onto main and changed testing environment to match (`Python 3.9`)
- started issue #29
- auditing the codebase (i.e., checking logging behavior for triggers)

**Blockers / questions:**
- N/A

**Next:**
- working on issue #29
## 2026-06-05
**Focus:** working on issue #23 and looking into algebraic data types

**Done today:**
- researched implementation of the Goal class via a GoalType enum rather than just string matching to make the implementation less fragile
- finished #23 by integrating into `npc.py` (removing the original goals parameter, since that was now handled by character)
- changed tests to use GoalType rather than strings

**Blockers / questions:**
- N/A

**Next:**
- rebasing onto other PRs and focusing on less string-matching implementations
## 2026-06-04
**Focus:** researching and watching lectures on AI

**Done today:**
- watched lecture on CLIN
- read through Reflexion paper
- skimmed through text adventure papers

**Blockers / questions:**
- N/A

**Next:**
- reading more papers while working on issues
## 2026-06-03
**Focus:** rebasing issue #4 onto main and looking into implementation of #9

**Done today:**
- Finished rebase of issue #4, adding reflections to the ReAct loop implementation on top of the Agent framework
- Discussed possible implementation details of emergent behavior with Alistair

**Blockers / questions:**
- Uncertain of which repository I should use for studying smallville's websocket implementation (both the original [Generative Agents](https://github.com/joonspk-research/generative_agents) repo and a separate [smallville](https://github.com/nmatter1/smallville) repo didn't use websocket)

**Next:**
- Finish issue #9
## 2026-06-02
**Focus:** read the ReAct paper and work on PR #4

**Done today:**
- Implemented the Reflect step in `npc.py`: on a failed action, the agent now receives the parser's actual precondition-failure message instead of the generic "Choose a different action" placeholder, so it knows *why* the action was blocked
- Added `Parser.last_fail_message` (and wired `WebParser.fail()` to set it too) so the reflect loop can read the failure reason without side-effects
- Capped retries at 2 (1 initial attempt + up to 2 reflect iterations)
- Added 3 tests in `tests/test_agent_layer.py` covering: failure reason surfaced in retry prompt, retry cap enforced, and reflect path through the hybrid behavior

**Blockers / questions:**
- N/A

**Next:**
- Open PR for #4, get review
- Look at hooking the agent loop into the live game (currently `npc.py` is not wired into `action_castle.py`)
## 2026-06-01
**Focus:** figuring out the interface between Python and Godot

**Done today:**
- Wrote a simple Python script to connect to Godot via UDP
	- ![[Screen Recording 2026-06-02 at 12.19.14 1.gif|240]]
- Finished lectures for "Search in AI" and "Classical Planning"

**Blockers / questions:**
- N/A

**Next:**
- Working on PR #4
