import { SectionHeading } from "./SectionHeading";

/**
 * "Reflections" — how this prototype was built, and what the coding agent that
 * helped build it was and was not good for.
 *
 * Deliberately placed after "What a day costs": the cost-scaling experiment
 * charted there is the worked example this section reflects on, and the numbers
 * quoted here ($8.02 for four cells, the ~70-second abort) are the ones recorded
 * in godot-generative-agents/runs/cost-scaling/ — the issue-921 comment thread
 * and orchestrator2.log respectively. Prose here follows the page's convention
 * of not citing issue numbers, which a reader cannot resolve until the
 * repository is public (#884).
 */
export function ReflectionsSection() {
  return (
    <section className="nrf-section">
      <div className="nrf-container">
        <div className="nrf-narrow">
          <SectionHeading id="reflections" level={2} className="nrf-title nrf-title-3 nrf-centered">
            Reflections: coding agents as research instruments
          </SectionHeading>
          <div className="nrf-content nrf-justified">
            <p>
              Much of this prototype was built with a coding agent in the loop — Claude Code,
              working against the repository the way a collaborator would: work specified as GitHub
              issues, implemented on feature branches, landed as pull requests a human read before
              merging. Its role grew past writing code into running the experiments. A
              live-simulation batch is a long, tedious, expensive errand, and each of the dozen-odd
              batches behind this page was driven end to end by the agent under a fixed protocol: a
              paid run under a hard cost cap, then analysis of the artifacts, then every behavior
              that looked wrong filed as its own sub-issue of the run log, so the evidence and the
              bug report stay attached.
            </p>
            <p>
              The cost figures above are the cleanest example. The agent designed and executed the
              measurement: it first audited the runs already on disk, which turned up three past
              runs of the exact showcase recipe — the baseline point and its error bar, for free —
              then laid out the rest as a one-factor-at-a-time sweep around that baseline and ran
              four cells in a single afternoon for <strong>$8.02</strong>. The other two are the{" "}
              <code>null</code> holes in the charts.
            </p>
            <p>
              They are holes because of the sort of failure only unattended automation finds.
              Partway through the cognition-tools cell the organization's API spending limit ran
              out. The engine handled it correctly, pausing the run after five consecutive provider
              errors — but the shell script driving the run only knew how to stop on budget
              exhausted or all steps done, and an error-pause is neither, so it polled a frozen run
              for forty minutes before a human noticed. The agent diagnosed it and fixed the driver
              to treat a paused run whose step count has stopped advancing as terminal. The fix
              validated itself the next morning: a transient provider flap killed a relaunched run
              at step 1, and the driver aborted after about seventy seconds having spent{" "}
              <strong>$0.00</strong>.
            </p>
            <p>
              The unreliability is worth stating plainly, because it was constant. For several of
              the bugs behind this prototype the mechanism initially hypothesized — sometimes in the
              issue text the agent itself wrote — turned out to be wrong, and was corrected only by
              evidence from a real run. Human judgment stayed load-bearing throughout: which
              experiment was worth its cost, whether a filed bug was really a bug, whether a diff
              should land at all. The agent made the expensive parts of this research cheap enough
              to actually do. It did not make the judgment optional.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
