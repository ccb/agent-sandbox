# Reading simulation output

Output messages carry a semantic `channel`, raw text, actor, turn, phase, and
optional metadata. Renderers choose presentation; tests and clients should assert
on channels rather than terminal formatting.

Important channel families include narration/system messages, action outcomes,
and private agent trace steps such as observation, reasoning, action, memory,
planning, and reflection. `JSONRenderer` is the structured boundary used by
out-of-process consumers. `CaptureRenderer` is the preferred test seam.

The live server additionally prints a run monitor with step progress, current
activity, model calls, failures, tokens, and estimated cost. A pause can mean the
step budget or cost ceiling was reached, repeated model errors triggered a safety
stop, or a user requested it. Inspect the status/health endpoints and server log
before resuming.

Replay frames show the world after each step. Events are sparse, semantic changes;
trace data explains an agent's cognition; wishes capture commands the current
action vocabulary could not ground. None of these should be interpreted as a
verbatim hidden chain of thought.
