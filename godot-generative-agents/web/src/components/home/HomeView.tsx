// ReactNode is only used by the Icon component below, which is commented out
// together with the link buttons that use it. Re-enable this import when you
// re-enable that block.
// import type { ReactNode } from "react";
import "./home.css";

// The Paper / arXiv / Video / Code buttons in the hero are commented out until
// the video (#881) and the public repository (#884, scheduled 2026-08-14)
// exist. Their inline SVG line-icons are commented out here along with them,
// since nothing else uses them. (The original Nerfies template pulls Font
// Awesome / Academicons from a CDN, which COOP/COEP would block — hence
// inlining.) Re-enable this block and the buttons together.
/*
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const PaperIcon = (
  <Icon>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
    <line x1="9" y1="13" x2="15" y2="13" />
    <line x1="9" y1="17" x2="15" y2="17" />
  </Icon>
);
const ArxivIcon = (
  <Icon>
    <path d="M22 10 12 5 2 10l10 5 10-5z" />
    <path d="M6 12v5c0 1 2.7 3 6 3s6-2 6-3v-5" />
  </Icon>
);
const VideoIcon = (
  <Icon>
    <circle cx="12" cy="12" r="9" />
    <polygon points="10 8 16 12 10 16" fill="currentColor" stroke="currentColor" />
  </Icon>
);
const CodeIcon = (
  <Icon>
    <path d="m9 18-6-6 6-6" />
    <path d="m15 6 6 6-6 6" />
  </Icon>
);
*/

// The repository this companion lives in. Swap for the standalone public repo
// when it publishes (#884).
const REPO_URL = "https://github.com/ccb/agent-sandbox";

/**
 * The public landing page (#879), styled after the Nerfies academic
 * project-page template (https://github.com/nerfies/nerfies.github.io).
 *
 * The narrative below covers the parts of the project that are settled:
 * credits, abstract, the agent architecture and its formalizations,
 * limitations, acknowledgements, and citations. Still to land here:
 *   TODO(#878): the selected-run case study (narrative + highlight timestamps).
 *   TODO(#881): the demo video embed in the teaser slot.
 *   TODO(#880): the "Run locally" guide and its nav entry.
 */
export function HomeView() {
  return (
    <div className="nrf">
      {/* ===== Hero: title, authors, affiliations, links ===== */}
      <section className="nrf-hero">
        <div className="nrf-hero-body">
          <div className="nrf-container nrf-centered">
            <h1 className="nrf-title nrf-title-1">
              Penn Campus: Generative Agents in a Simulated World
            </h1>
            <p className="nrf-venue">PURM 2026 · University of Pennsylvania</p>

            <div className="nrf-authors">
              <span className="nrf-author-block">
                <a href="https://github.com/aking526">Alistair King</a>,
              </span>{" "}
              <span className="nrf-author-block">
                <a href="https://github.com/0frankie">Frankie L</a>
              </span>
            </div>

            {/* Everyone shares one affiliation, so no superscripts are needed. */}
            <div className="nrf-affiliations">University of Pennsylvania</div>
            <div className="nrf-advisor">
              Advised by <a href="https://www.cis.upenn.edu/~ccb/">Chris Callison-Burch</a>
            </div>

            {/* Paper / arXiv / Video / Code links — re-enable (along with the
                Icon block at the top of this file) once the video (#881) and
                public repository (#884) URLs exist.

            <div className="nrf-links">
              <a className="nrf-button" href="#">
                {PaperIcon}
                <span>Paper</span>
              </a>
              <a className="nrf-button" href="#">
                {ArxivIcon}
                <span>arXiv</span>
              </a>
              <a className="nrf-button" href="#">
                {VideoIcon}
                <span>Video</span>
              </a>
              <a className="nrf-button" href={REPO_URL} target="_blank" rel="noreferrer">
                {CodeIcon}
                <span>Code</span>
              </a>
            </div>
            */}
          </div>
        </div>
      </section>

      {/* ===== Teaser: summary + link into the replay =====
          TODO(#881): embed the captioned demo video here once it's published.
          TODO(#878): swap in a still from the selected showcase run meanwhile. */}
      <section className="nrf-teaser">
        <div className="nrf-container">
          <p className="nrf-subtitle nrf-centered nrf-teaser-cap">
            Five LLM-driven agents plan, remember, and converse their way through a twelve-hour day
            on a faithful tile map of Penn's campus — and every run replays deterministically, right
            in your browser.
          </p>
          <div className="nrf-links">
            <a className="nrf-button" href="#game">
              <span>Open the replay demo →</span>
            </a>
          </div>
        </div>
      </section>

      {/* ===== Abstract ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow nrf-centered">
            <h2 className="nrf-title nrf-title-3">Abstract</h2>
            <div className="nrf-content nrf-justified">
              <p>
                We place five generative agents — characters driven by a large language model, with
                persistent memory, daily plans, and the ability to hold conversations — on a tile
                map of the University of Pennsylvania's campus derived from real OpenStreetMap data.
                Over a simulated twelve-hour day the agents walk between real campus places, pursue
                individually authored goals, and strike up conversations whose outcomes feed back
                into their plans and memories, following the memory–reflection–planning architecture
                of Park et al.'s <em>Generative Agents</em>.
              </p>
              <p>
                The simulation is built on a classical text-adventure engine: every action an agent
                takes — whether proposed by a language model or by a scripted schedule — must pass
                the same precondition/effect gate before it can change the world, so the model never
                mutates state directly. Each run records its LLM traffic and world seed, which makes
                any run replayable deterministically in a Godot viewer, natively or in the browser
                via WebAssembly.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Architecture ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered">How an agent works</h2>
            <div className="nrf-content nrf-justified">
              <h3 className="nrf-title nrf-title-4">The world and its clock</h3>
              <p>
                The world advances in discrete ticks of ten in-game seconds, so an hour is 360 ticks
                and the showcase's twelve-hour day is 4,320. On each tick, every agent that is not
                mid-walk, settled into an activity, or mid-conversation makes a decision; decisions
                are then resolved in a fixed order, so two agents contending for the same resource
                settle deterministically. An agent perceives the world through a limited window: it
                observes a thing at tile <em>p′</em> from its own tile <em>p</em> only when the two
                are within a Chebyshev radius <em>r</em> = 8,
              </p>
              <div className="nrf-math">
                ‖p − p′‖<sub>∞</sub> = max(|Δx|, |Δy|) ≤ r,
              </div>
              <p>
                and anything newly entering that window — an event, or another agent's arrival —
                becomes an observation in its memory stream.
              </p>

              <h3 className="nrf-title nrf-title-4">Memory and retrieval</h3>
              <p>
                Everything an agent experiences — observations, its own actions and failures, lines
                of dialogue, plans, reflections — is a timestamped record with an importance score.
                When the agent must decide, it cannot see the whole stream; it retrieves the records
                that score highest under a weighted sum of recency, importance, and relevance to the
                current situation <em>q</em> at tick <em>t</em>:
              </p>
              <div className="nrf-math">
                s(m, q, t) = α<sub>rec</sub> · γ<sup>t − a(m)</sup> + α<sub>imp</sub> · i(m) / 10 +
                α<sub>rel</sub> · rel(q, m)
              </div>
              <p>
                with decay γ = 0.95 per tick since the record was last accessed (<em>a(m)</em>),
                importance <em>i(m)</em> ∈ [1, 10] normalized to unit range, and all weights α = 1.
                Relevance is keyword overlap between the query and the record by default; when an
                embedding backend is configured it becomes cosine similarity rescaled to the same
                [0, 1] range, rel(q, m) = (1 + cos(v<sub>q</sub>, v<sub>m</sub>)) / 2. The top six
                records within a ~800-token budget are surfaced into the decision prompt. Retrieval
                refreshes a record's last-accessed time, so memories the agent keeps returning to
                stay warm while the rest fade.
              </p>

              <h3 className="nrf-title nrf-title-4">Importance and reflection</h3>
              <p>
                New memories are rated for poignancy by the language model on a 1 (utterly mundane)
                to 10 (momentous) scale, in one batched, temperature-zero call per agent per tick. A
                few signals the model cannot infer from text — like falling ill, or a commitment
                made in conversation — carry fixed scores instead. Reflection is triggered by
                accumulated salience rather than by the clock: once the summed importance of
                memories since the last reflection crosses a threshold θ = 30,
              </p>
              <div className="nrf-math">
                Σ<sub>m since last reflection</sub> i(m) ≥ θ,
              </div>
              <p>
                the agent asks itself up to three salient questions about its recent experience,
                answers each from retrieved evidence, and writes the inferences back into memory as
                higher-level reflections that cite the records they were drawn from — so later
                decisions can build on conclusions, not just raw observations.
              </p>

              <h3 className="nrf-title nrf-title-4">Planning</h3>
              <p>
                Each agent starts its day by decomposing intentions hierarchically: a day outline,
                refined into hourly blocks, refined into minute-level stops — each stop a real
                place, an activity, and a duration. Proposed stops are validated against the actual
                map, so a hallucinated location is dropped before it can reach the world. Plans are
                living documents: an agent revises when it falls behind schedule, when an action is
                rejected by the world, when a conversation changes its commitments, or when it
                reacts to something it perceives.
              </p>

              <h3 className="nrf-title nrf-title-4">Conversations</h3>
              <p>
                When two agents are close, free, and interested, they open a conversation that
                unfolds one line per tick, up to six exchanges — dialogue takes simulated time
                rather than resolving instantly. Afterwards each participant distills an outcome:
                what was agreed, what it means for their relationship, and whether their plans
                should change; commitments and relationship notes are written to memory with high
                importance so they survive retrieval competition. A pair that has already talked{" "}
                <em>n</em> times waits min(n, 3) × 90 ticks before starting again, which keeps two
                friendly agents from looping the same greeting all day.
              </p>

              <h3 className="nrf-title nrf-title-4">The action gate</h3>
              <p>
                Every decision — whether it arrives as a typed tool call from the model or as plain
                text — is reassembled into a command and pushed through the engine's parser, where
                the action's preconditions are checked before its effects apply. The model never
                edits world state. A rejected action is not silent: it becomes a failure memory and
                can trigger a plan revision, so agents learn from what the world refuses.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* TODO(#878): selected-run case study goes here — narrative, highlight
          timestamps, and provenance (provider, model, effort, seed, cost). */}

      {/* ===== Limitations ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered">Limitations</h2>
            <div className="nrf-content nrf-justified">
              <p>
                This is a small research prototype, and it is honest about it. The generative
                machinery — conversation, reflection, importance scoring, plan revision — runs only
                when a real language-model provider is attached; the offline default is a
                deterministic mock brain replaying authored schedules, which we use for testing and
                byte-identical replay baking. Memory relevance defaults to keyword overlap, with
                embedding-based similarity as an opt-in. Reproducibility comes from recording each
                run's LLM traffic and world seed and replaying both, not from seeding the model
                itself. And the scale is deliberately modest — five agents, one campus, one
                simulated day — so the behaviors you'll see are believable vignettes, not validated
                claims about human behavior.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Acknowledgements ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered">Acknowledgements</h2>
            <div className="nrf-content nrf-justified">
              <p>
                This project was carried out through the Penn Undergraduate Research Mentoring
                Program (PURM), advised by{" "}
                <a href="https://www.cis.upenn.edu/~ccb/">Chris Callison-Burch</a>. It builds on the{" "}
                <code>agent-sandbox</code> multi-agent simulation framework and the text-adventure
                engine from Chris Callison-Burch's interactive-fiction course materials, and we
                thank the framework's broader contributors. Character sprite art is from the{" "}
                <em>Cute Fantasy</em> pack by Kenmi. Campus geography is derived from{" "}
                <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> data.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== References ===== */}
      <section className="nrf-section">
        <div className="nrf-container">
          <div className="nrf-narrow">
            <h2 className="nrf-title nrf-title-3 nrf-centered">References</h2>
            <div className="nrf-content">
              <p>
                Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy
                Liang, and Michael S. Bernstein. 2023.{" "}
                <a href="https://dl.acm.org/doi/10.1145/3586183.3606763">
                  Generative Agents: Interactive Simulacra of Human Behavior
                </a>
                . In <em>Proceedings of UIST '23</em>.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== BibTeX ===== */}
      <section className="nrf-section" id="BibTeX">
        <div className="nrf-container nrf-content">
          <h2 className="nrf-title nrf-title-3">BibTeX</h2>
          <pre className="nrf-pre">
            <code>{`@misc{king2026penncampusagents,
  title  = {Penn Campus: Generative Agents in a Simulated World},
  author = {King, Alistair and L, Frankie and Callison-Burch, Chris},
  year   = {2026},
  note   = {PURM, University of Pennsylvania},
  url    = {${REPO_URL}},
}`}</code>
          </pre>
        </div>
      </section>

      {/* ===== Footer: template attribution (as the Nerfies license asks) ===== */}
      <footer className="nrf-footer">
        <div className="nrf-container">
          <div className="nrf-content nrf-footer-content">
            <p>
              The design of this page is adapted from the{" "}
              <a href="https://github.com/nerfies/nerfies.github.io">Nerfies</a> project page. We
              thank the authors for releasing their{" "}
              <a href="https://github.com/nerfies/nerfies.github.io">source code</a>, which is
              licensed under a{" "}
              <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">
                Creative Commons Attribution-ShareAlike 4.0 International License
              </a>
              .
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
