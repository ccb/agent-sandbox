import { SectionHeading } from "./SectionHeading";

/**
 * "Run locally" — the public guide to running the simulation on your own
 * machine, in the Godot native app (#880). The deployed site is documentation
 * and a replay: it never receives an API key and never makes a request to the
 * reader's machine.
 *
 * Command blocks are inline template literals rendered as plain <pre> (the
 * BibTeX pattern) rather than snippet files: tests/test_landing_snippets.py
 * pins snippet files against engine source, and shell commands have no source
 * to pin against.
 *
 * Engine-modification instructions (new verbs, new worlds) are deliberately a
 * one-line "coming soon" — they ship with the public code package (#884).
 */

const MOCK_RUN = `uv sync --extra server

# Terminal 1 — serve the simulation (mock brain: real requests, zero spend):
uv run python godot-generative-agents/backend/penn/serve_penn.py

# Terminal 2 — point the viewer at it:
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh`;

const LLM_RUN = `uv sync --extra server --extra llm   # one-time: adds the Anthropic SDK

# Terminal 1 — serve with the real brain (boots paused; no calls yet):
export ANTHROPIC_API_KEY=your-key-here
uv run python godot-generative-agents/backend/penn/serve_penn.py \\
  --brain llm --steps 360 --max-cost 1.00

# Terminal 2 — the viewer, exactly as before:
SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh`;

export function RunLocallySection() {
  return (
    <section className="nrf-section">
      <div className="nrf-container">
        <div className="nrf-narrow">
          <SectionHeading id="run-locally" level={2} className="nrf-title nrf-title-3 nrf-centered">
            Run locally
          </SectionHeading>
          <div className="nrf-content nrf-justified">
            <p>
              Everything above can be reproduced on your own machine: the same simulation the{" "}
              <a href="#demo">demo</a> replays, driven live by a language model you pay for
              directly. The whole workflow is local — your API key is read from your environment by
              a process on your machine, and is never sent to, stored by, or proxied through this
              site. The deployed page you are reading makes no request to your machine.
            </p>
            <p>
              <strong>One honest caveat up front:</strong> the public code package is scheduled for{" "}
              <strong>August 14, 2026</strong>. Until then this guide documents exactly what that
              package will contain, so it reads as a preview rather than a walkthrough you can
              finish today.
            </p>

            <SectionHeading id="prereqs" level={3} className="nrf-title nrf-title-4">
              Prerequisites
            </SectionHeading>
            <ul>
              <li>
                <strong>Python 3.12</strong> with <a href="https://docs.astral.sh/uv/">uv</a> —{" "}
                <code>uv sync</code> creates the environment from the committed lockfile; no manual
                venv management.
              </li>
              <li>
                <strong>Godot 4.6</strong> — on your <code>PATH</code> as <code>godot</code> (or{" "}
                <code>godot4</code>), or installed as the standard macOS app bundle; the launcher
                looks in those three places, in that order.
              </li>
              <li>
                An <strong>Anthropic API key</strong> — only for the real-model run below; the mock
                run needs no key at all.
              </li>
            </ul>

            <SectionHeading id="mock-run" level={3} className="nrf-title nrf-title-4">
              Try it free first
            </SectionHeading>
            <p>
              The backend ships a deterministic mock brain: the full server, the full viewer, real
              HTTP traffic between them — and no model calls, so no key and no spend. Two terminals,
              from the repository root:
            </p>
            <pre className="nrf-pre">
              <code>{MOCK_RUN}</code>
            </pre>
            <p>
              The mock run starts itself; the viewer's landing menu connects and follows the day as
              it ticks. If the window opens and agents walk the campus, everything is installed
              correctly — the real-model run below reuses this exact plumbing.
            </p>

            <SectionHeading id="key-and-cost" level={3} className="nrf-title nrf-title-4">
              Your key, and what a run costs
            </SectionHeading>
            <p>
              The server reads <code>ANTHROPIC_API_KEY</code> from the environment (or from a{" "}
              <code>.env</code> file at the repository root; already-exported variables win). No
              other key variable is consulted. The key is verified at boot with one free models-list
              request, so a typo'd or revoked key stops the server with a one-line fix instead of a
              silently frozen simulation.
            </p>
            <p>
              Expect real, if modest, spend: the showcase recipe — five agents, twelve simulated
              hours — measured <strong>$5.4–6.8 per run</strong>, scaling roughly linearly with
              duration (about $0.49 per simulated hour) and with cast size past three agents. The
              measurements are charted in <a href="#cost">What a day costs</a>. The configuration's{" "}
              <code>max_cost_usd</code> kill-switch (default $5) hard-stops a run that overshoots —
              raise it deliberately for a full-length day, or shorten the day instead.
            </p>

            <SectionHeading id="two-terminal-flow" level={3} className="nrf-title nrf-title-4">
              Run it
            </SectionHeading>
            <pre className="nrf-pre">
              <code>{LLM_RUN}</code>
            </pre>
            <p>
              Under <code>--brain llm</code> the loop boots <em>paused</em>: not a single paid model
              call is made until you start the run yourself. When the viewer connects to a backend
              paused at tick zero, it opens the <strong>setup scene</strong> — pick the cast from
              the persona library, choose the planner, model, and thinking effort, set the day
              length, and adjust the retrieval, perception, and conversation knobs. Press{" "}
              <strong>Start</strong> and the viewer drops into the campus to follow the run live;
              every knob you chose is recorded into the run's manifest so it can be reproduced.
            </p>

            <SectionHeading id="run-troubleshooting" level={3} className="nrf-title nrf-title-4">
              If something goes wrong
            </SectionHeading>
            <ul>
              <li>
                <em>"Godot 4 not found."</em> — the launcher probes <code>godot</code>,{" "}
                <code>godot4</code>, then the macOS app bundle. Install Godot 4.6 or put it on your{" "}
                <code>PATH</code> under one of those names.
              </li>
              <li>
                <em>Import errors about the LLM extra</em> — <code>--brain llm</code> needs{" "}
                <code>uv sync --extra server --extra llm</code>; the server exits with that exact
                instruction if the SDK is missing.
              </li>
              <li>
                <em>Missing or invalid key</em> — the server refuses to start without{" "}
                <code>ANTHROPIC_API_KEY</code>, and aborts at boot if the key doesn't verify. You
                will never get the worst version of this failure: a day that ticks normally while
                every agent sits frozen at $0 spend.
              </li>
              <li>
                <em>"Can't reach … — is the backend running?"</em> in the viewer's menu — start
                terminal 1 first, and check the URL matches the server's <code>--host</code>/
                <code>--port</code> (default <code>http://127.0.0.1:8080</code>).
              </li>
              <li>
                <em>Port already in use</em> — another process owns 8080; pass <code>--port</code>{" "}
                to the server and match it in <code>SIM_API_URL</code>.
              </li>
            </ul>

            <SectionHeading id="extending" level={3} className="nrf-title nrf-title-4">
              Make it your own
            </SectionHeading>
            <p>
              The simulation runs on a general text-adventure engine — new verbs, new worlds, and
              new agent faculties are all ordinary extensions of it. Instructions for modifying the
              engine are coming soon, alongside the public code package on August 14.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
