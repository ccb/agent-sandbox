import { repoFile, repoTree } from "./links";
import { SectionHeading } from "./SectionHeading";

/**
 * "Run locally" — a pointer, not a guide (#880, scope narrowed 2026-08-04). The
 * prerequisites, the free mock run, key configuration, cost, and the
 * two-terminal launch all live in `godot-generative-agents/README.md` on the
 * `prod` branch; duplicating them here meant two copies drifting apart, and the
 * README is the one a reader lands in anyway once they have the code.
 *
 * The deployed site is documentation and a replay: it never receives an API key
 * and never makes a request to the reader's machine — that promise stays on the
 * page because it is about *this* page.
 */

const README_URL = repoFile("godot-generative-agents/README.md");

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
              Everything above runs on your own machine: the same simulation behind the{" "}
              <a href="#demo">demo</a>, freshly run and driven live by a language model you pay for
              directly — a local backend and the Godot viewer, two terminals from a fresh checkout.
              The whole workflow is local, so your API key is read from your environment by a
              process you started and is never sent to, stored by, or proxied through this site,
              which makes no request to your machine at all. Prerequisites, the free mock run that
              spends nothing, key configuration, measured costs, and the two-terminal launch are
              documented in{" "}
              <a href={README_URL} target="_blank" rel="noreferrer">
                <code>godot-generative-agents/README.md</code>
              </a>{" "}
              in the{" "}
              <a href={repoTree} target="_blank" rel="noreferrer">
                repository
              </a>
              , where they stay in step with the code instead of being restated here. New verbs, new
              worlds, and new agent faculties are all ordinary extensions of the general
              text-adventure engine underneath, and instructions for modifying it ship alongside the
              code package.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
