"""The scripted full-feature mock brain (issue #563).

A deterministic, key-free brain that -- unlike ``ScheduleMockClient`` -- is a
*distinct* client object, so the identity gate ``_use_action_tools`` (``brain is
not agent.schedule``) opens and every ``llm_client``-gated Penn path runs
offline: the per-verb tool loop (#485), cognition tools (#358/#512),
conversation (#86), and reflection (#84).

It follows each persona's authored schedule by reading a ``{name:
ScheduleMockClient}`` map that :func:`backend.cognition.attach_agents` registers
on it, so agents still reach their rendezvous and conversations fire. Every
response is a pure function of the prompt plus that (deterministic) schedule
state -- never a call counter, because the client is shared across personas and
decisions may run in parallel (#366).
"""

from backend.cognition import first_line_location
from text_adventure_games.llm_client import MockLlmClient


def _last_user_content(messages) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"]
    return ""


def _has_tool_result(messages) -> bool:
    """True once run_tool_loop has appended a tool_result block (i.e. a cognition
    call already ran this decide episode). Pure function of the prompt."""
    for m in messages or []:
        content = m.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            return True
    return False


def _line_for(actor) -> str:
    return f"Hello, it's {actor or 'me'} -- good to see you."


class ScriptedPennBrain(MockLlmClient):
    """A distinct ``MockLlmClient`` that follows registered schedules."""

    def __init__(self, ledger=None):
        # Bind our own methods as the responders so MockLlmClient's recording /
        # logging (ledger, tool_calls_log) is reused verbatim. The bound methods
        # close over self, so they can read self.context / self._schedules.
        super().__init__(
            tool_calls_responses=self._on_call_tools,
            tool_responses=self._on_call_tool,
            responses=self._on_chat,
            ledger=ledger,
        )
        self._schedules: dict[str, object] = {}

    def register_schedule(self, name: str, schedule) -> None:
        self._schedules[name] = schedule

    # -- responders ---------------------------------------------------------

    def _on_call_tools(self, messages, tools, tool_choice, max_tokens, temperature):
        names = {t.get("name") for t in tools}
        # Consult memory once (if offered) before speaking OR acting, so the
        # cognition-tool loop (#358) is exercised on BOTH paths: decide (recall
        # alone) and converse (recall offered alongside speak, #512's
        # _converse_with_cognition). Round 2 -- a tool_result is already present
        # -- falls through to the speak/decide below.
        if "recall" in names and not _has_tool_result(messages):
            return {
                "tool_calls": [{"name": "recall", "arguments": {"query": "my plan"}}]
            }
        if "speak" in names:
            actor = (self.context or {}).get("actor")
            return {
                "tool_calls": [
                    {
                        "name": "speak",
                        "arguments": {"utterance": _line_for(actor), "done": True},
                    }
                ]
            }
        return self._decide(messages, tools)

    def _on_call_tool(self, messages, tool, max_tokens, temperature):
        if tool.get("name") == "speak":
            actor = (self.context or {}).get("actor")
            return {"utterance": _line_for(actor), "done": True}
        return None

    def _on_chat(self, messages, max_tokens, temperature):
        return None  # decide/converse go through the tool routes.

    # -- decide -------------------------------------------------------------

    def _decide(self, messages, tools):
        actor = (self.context or {}).get("actor")
        schedule = self._schedules.get(actor)
        observation = _last_user_content(messages)
        if schedule is None:
            # No schedule registered (safety): act in place so the loop advances.
            return {
                "tool_calls": [
                    {
                        "name": "perform",
                        "arguments": {
                            "activity": "looking around",
                            "reasoning": "no plan",
                        },
                    }
                ]
            }
        destination = schedule.destination
        if first_line_location(observation) != destination.lower():
            return {
                "tool_calls": [
                    {
                        "name": "travel",
                        "arguments": {
                            "destination": destination,
                            "reasoning": f"heading to {destination}",
                        },
                    }
                ]
            }
        return {
            "tool_calls": [
                {
                    "name": "perform",
                    "arguments": {
                        "activity": schedule.activity,
                        "reasoning": "settling in",
                    },
                }
            ]
        }


def _reflect_responder(messages, tool, max_tokens, temperature):
    """Answer LLMReflector's two tools with schema-valid, deterministic replies."""
    name = tool.get("name")
    if name == "salient_questions":
        return {"questions": ["What am I learning as my day unfolds?"]}
    if name == "record_insight":
        return {
            "insight": "I move between campus places to keep my plan.",
            "evidence": [1],
        }
    return None


def build_scripted_brains(ledger=None, decide_ledger=None, reflect_ledger=None):
    """Return ``(brain, reflector)`` for a --brain scripted run.

    Both record into ``ledger`` so GET /usage / the run log are non-empty
    offline. Pass ``decide_ledger`` / ``reflect_ledger`` to record each role
    through its own view instead (they default to ``ledger``) -- the live server
    passes monitor-tagged (:class:`RoleTaggedLedger`) views so
    ``serve_penn --brain scripted --monitor`` prints decide/converse vs reflect
    request lines, exactly like the paid brain."""
    brain = ScriptedPennBrain(ledger=decide_ledger or ledger)
    reflector = MockLlmClient(
        tool_responses=_reflect_responder, ledger=reflect_ledger or ledger
    )
    return brain, reflector
