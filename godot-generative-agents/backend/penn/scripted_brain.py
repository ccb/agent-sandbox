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

from text_adventure_games.llm_client import MockLlmClient


def _first_line_location(observation: str) -> str:
    """``describe_for`` puts the location name (UPPERCASE) on the first non-empty
    line; mirror ``ScheduleMockClient._current_location`` (lowercased)."""
    for line in (observation or "").splitlines():
        if line.strip():
            return line.strip().lower()
    return ""


def _last_user_content(messages) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"]
    return ""


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
        # (converse + cognition branches are added in Task 3.)
        return self._decide(messages, tools)

    def _on_call_tool(self, messages, tool, max_tokens, temperature):
        return None  # (speak fallback is added in Task 3.)

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
        if _first_line_location(observation) != destination.lower():
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
