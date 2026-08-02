/**
 * "One day on campus" — the selected-run case study (#878 → #879).
 *
 * The narrative and every timestamp below describe the exact replay the demo
 * at the top of the page plays: `run-20260730-150317-7ed039`, the #878
 * showcase pick (batch 12 of the #760 run log; selection evidence and the
 * equality-proven freeze are on those issues). Steps are scrubbable in the
 * demo's timeline, so the table doubles as a viewing guide. The cost figure is
 * imported from CostSection's pinned replicates rather than restated, so the
 * two sections cannot drift apart.
 */

import { BASELINE_REPLICATES } from "./CostSection";

/** The frozen showcase run's identity and provenance (#878). */
export const RUN = {
  id: "run-20260730-150317-7ed039",
  agents: 5,
  steps: 4320,
  simHours: 12,
  // Batch 12 is the first baseline replicate — see CostSection's docstring.
  costUsd: BASELINE_REPLICATES[0],
  calls: 906,
  failedCalls: 0,
  seed: 42,
  effort: "medium",
  conversations: 20,
  commitments: 21,
  verbs: 11,
} as const;

/** The sim clock starts at 08:00 and advances 10 s per step. */
export const SIM_START_HOUR = 8;
export const SECONDS_PER_STEP = 10;

/** The viewer's sim-clock label ("HH:MM") for a replay step. */
export function stepClock(step: number): string {
  const minutes = Math.floor((step * SECONDS_PER_STEP) / 60);
  const hh = SIM_START_HOUR + Math.floor(minutes / 60);
  const mm = minutes % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/**
 * The day's highlights, in step order — what to scrub to and watch. Each
 * `moment` states only what the replay shows; the narrative above the table
 * carries the interpretation.
 */
export const HIGHLIGHTS: { step: number; moment: string }[] = [
  {
    step: 0,
    moment: "Five agents wake into their plans; Maya and Priya agree to meet at Van Pelt.",
  },
  {
    step: 71,
    moment:
      "Tanaka preps Irvine Auditorium — AV checks, projector test, handouts (a 💭 wish bubble in the viewer).",
  },
  { step: 537, moment: "Mateo reports the auditorium's AV setup to Tanaka." },
  {
    step: 705,
    moment:
      "The gravitational-waves lecture begins: Tanaka front and center, Mateo running the booth.",
  },
  { step: 814, moment: "Tanaka thanks Mateo for the seamless live LIGO-data transition." },
  {
    step: 848,
    moment: "Maya and Priya settle into Chapter 5, problem 3, in the Moelis Reading Room.",
  },
  { step: 1151, moment: "Theo, who skipped the lecture, asks Mateo how it went." },
  {
    step: 1437,
    moment: "Priya catches Tanaka with a question; an impromptu whiteboard session follows.",
  },
  { step: 1643, moment: "Theo and Mateo debate the lecture's determinism angle over lunch." },
  { step: 2514, moment: "Priya starts pulling and cleaning a dataset for her course project." },
  {
    step: 3573,
    moment: "Maya and Theo bump into each other in the Book Stacks — “funny running into you.”",
  },
  { step: 3725, moment: "Theo studies free will and determinism for his seminar paper." },
  { step: 4026, moment: "Mateo meets his sister Elena at College Hall as the day winds down." },
];

export function CaseStudySection() {
  return (
    <section className="nrf-section">
      <div className="nrf-container">
        <div className="nrf-narrow">
          <h2 className="nrf-title nrf-title-3 nrf-centered" id="case-study">
            One day on campus
          </h2>
          <div className="nrf-content nrf-justified">
            <p>
              The <a href="#demo">demo above</a> plays one specific day — the run we selected and
              froze for this page: {RUN.agents} agents, {RUN.steps.toLocaleString()} steps, a
              twelve-hour simulated day from 08:00 to 20:00. The personas and the campus are
              authored; the day is not. Every plan, conversation, and change of mind below came out
              of the loop described above, one gated action at a time.
            </p>
            <p>
              The day organizes itself around a morning physics lecture in Irvine Auditorium — and
              the interesting part is what the lecture sets in motion everywhere else. Professor
              Tanaka arrives early to check the AV equipment and lay out handouts. Mateo Vasquez —
              on campus visiting his sister — helps in the booth, confirms the setup with Tanaka,
              and runs the live LIGO-data segments when the lecture starts. ("That transition into
              the live LIGO data was seamless," Tanaka tells him afterward — praise grounded in a
              thing that actually happened.) Maya Chen and Priya Nair spend the same morning on a
              different track entirely: a reserved organic-chemistry textbook at the Van Pelt
              circulation desk, a coffee run, and a shared assault on problem 3 in the Moelis
              Reading Room.
            </p>
            <p>
              The afternoon belongs to the lecture's ripples, which is the property the memory
              stream exists to produce: behavior hours later, grounded in an earlier interaction.
              Priya catches Tanaka at noon with a question about matched filtering and gets an
              impromptu whiteboard session — then spends the rest of her day pulling and cleaning a
              dataset for her course project. Theo Lindqvist, who skipped the lecture, hears about
              it from Mateo, debates its determinism angle with him over lunch, and by evening is
              deep in the stacks reading up on free will and determinism for his seminar paper. At
              17:55 Maya and Theo bump into each other in the Book Stacks, and Maya leaves with a
              campus history book on top of her orgo notes.
            </p>
            <p>
              Two soft spots, kept rather than edited out. At 14:31 Maya sets off for a seminar she
              confidently misremembers as being at Houston Hall; 57 minutes later a mid-walk
              decision corrects her to College Hall, and she is taking notes at the real seminar by
              15:44 — a model slip, but the correction machinery doing exactly its job. And Mateo
              spends stretches of the mid-afternoon idling around Houston Hall between his morning
              AV work and his evening walk — honest empty time, labeled as such.
            </p>
          </div>

          <table className="nrf-moments">
            <caption>
              Where to scrub to — sim clock and timeline step of each moment, in the demo's
              timeline.
            </caption>
            <thead>
              <tr>
                <th scope="col">Clock</th>
                <th scope="col">Step</th>
                <th scope="col">What happens</th>
              </tr>
            </thead>
            <tbody>
              {HIGHLIGHTS.map(({ step, moment }) => (
                <tr key={step}>
                  <td>{stepClock(step)}</td>
                  <td>{step.toLocaleString()}</td>
                  <td>{moment}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="nrf-content nrf-justified">
            <p>
              Provenance: run <code>{RUN.id}</code>, seed {RUN.seed}, reasoning effort {RUN.effort},
              cognition tools on, with the model tiering described above — the deliberative roles on
              the larger model, conversation on the cheaper one. The day cost{" "}
              <strong>${RUN.costUsd.toFixed(2)}</strong> across {RUN.calls} model calls (
              {RUN.failedCalls} failed) and produced {RUN.conversations} conversations,{" "}
              {RUN.commitments} remembered commitments, and {RUN.verbs} distinct verbs at the action
              gate. It is also the five-agent baseline in the cost section below; the run log
              records the selection evidence against the other candidate.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
