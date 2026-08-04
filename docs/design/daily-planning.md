# Daily planning

Daily planning decomposes an agent's broad day into hourly summaries and grounded
stops. A stop names a real world place, activity, optional display emoji, and
duration. The scheduler turns stops into travel and settled activity; live
cognition can revise the remaining tail when the agent falls behind or encounters
new information.

Plans are context, not commands. Every resulting action still passes through the
normal parser/tool schema and engine preconditions. Planner tests should pin
place grounding, duration bounds, deterministic mock behavior, and revision
cooldowns.
