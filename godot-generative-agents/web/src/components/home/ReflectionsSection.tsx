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
              working against the repository the way a collaborator would. Work was specified as
              GitHub issues, implemented on feature branches, and landed as pull requests that a
              human read before merging. Over time the agent's role grew past writing code into
              running the experiments: a live-simulation batch is a long, tedious, and expensive
              errand, and each of the dozen-odd batches behind this page was driven end to end by
              the agent under a fixed protocol: a paid run under a hard per-run cost cap; then
              analysis of the artifacts; then every behavior that looked wrong filed as its own
              sub-issue of the run log, so the evidence and the bug report stay attached.
            </p>
            <p>
              The cost figures in the section above are the cleanest example. The measurement was
              specified as an experiment — how does a simulated day's bill scale with cast size,
              with simulated duration, and with the agents' cognition tools — and the agent designed
              and executed it. It began by auditing the runs already on disk to find which cells of
              the matrix were answerable for free, which turned up three past runs of the exact
              showcase recipe that became the baseline point and its error bar at no cost; it then
              laid out the remaining cells as a one-factor-at-a-time sweep around that baseline, and
              ran four of them sequentially in a single afternoon for <strong>$8.02</strong>. The
              remaining two cells are the <code>null</code> holes in the charts above.
            </p>
            <p>
              They are holes because the experiment ran into the sort of failure that only
              unattended automation finds. Partway through the cognition-tools cell the
              organization's API spending limit ran out; the engine handled it correctly, pausing
              the simulation after five consecutive provider errors, but the shell script driving
              the run only knew how to stop on two conditions — budget exhausted, or all steps done
              — and an error-pause is neither. It polled a frozen run for forty minutes before a
              human noticed. The agent diagnosed the loop, filed it, fixed it to treat a paused run
              whose step count has stopped advancing as terminal, and verified both directions. The
              fix then validated itself in production the next morning: a transient provider flap
              killed a relaunched run at step 1, and the driver aborted after about seventy seconds
              having spent <strong>$0.00</strong>, artifacts captured and the run marked aborted.
            </p>
            <p>
              What made that comfortable to run unattended is the same principle this paper argues
              for in the simulation itself. Inside a run, a language model never mutates the world:
              it proposes an action, and a precondition gate disposes. Working with a coding agent
              had exactly that shape. The agent proposes; hard gates decide. The cost cap is
              enforced by the driver, not by the agent's intentions. The test suite gates what gets
              published — the numbers in the charts above are pinned to the recorded run data, and
              the suite fails if the prose and the CSV drift apart. Human review gates every merge.
              None of these are sophisticated, and that is rather the point: cheap mechanical checks
              at the boundaries are what turned a capable but unreliable collaborator into an
              instrument we were willing to leave running.
            </p>
            <p>
              The unreliability is worth stating plainly, because it was constant. The agent
              mispredicted causes routinely: for several of the bugs behind this prototype, the
              mechanism initially hypothesized — sometimes in the issue text the agent itself wrote
              — turned out to be wrong, and was corrected only by evidence from a real run.
              Automation hides its own failure modes until they trip, and the spinning run-driver
              above was discovered by a real API limit rather than by anyone thinking to test for
              it. And across all of it, human judgment stayed load-bearing: deciding which
              experiment was worth its cost, whether a filed bug was really a bug, and whether a
              diff should land at all. The agent made the expensive parts of this research cheap
              enough to actually do. It did not make the judgment optional.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
