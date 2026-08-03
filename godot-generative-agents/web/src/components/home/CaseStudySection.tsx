import { CodeRef } from "./CodeRef";
import { SectionHeading } from "./SectionHeading";

/**
 * "One simulated day, up close" — the #878 case study of the showcase run.
 *
 * Comes right after the demo and abstract: watch the day, then read it beat by
 * beat, then (in the architecture section) the machinery behind it. Every
 * quotation below — dialogue lines, plan memories, reflections — is copied
 * verbatim from `public/replay/penn_replay.json`, the same file the demo at
 * the top of the page plays, and `CaseStudySection.test.ts` pins each one to
 * the record it came from, so the prose cannot drift from the data. Judge
 * scores are hand-copied from the run's believability audit
 * (`runs/issue-760-batch-12/runA/believability.md`) and pinned in the same
 * test.
 */

/** Provenance of the showcase run, pinned to the replay's `meta` block. */
export const RUN = {
  id: "run-20260730-150317-7ed039",
  seed: 42,
  engineSha: "51415dc1",
  steps: 4320,
  secPerStep: 10,
  start: "2023-02-13 08:00:00",
  planModel: "claude-sonnet-5",
  liveModel: "claude-haiku-4-5",
  planMode: "llm",
  costUsd: 5.37355, // usage.json total_cost_usd; equals CostSection's first baseline replicate
  conversations: 20, // run.yaml `result.conversations`
  events: 132,
};

/** Sim wall clock for a turn: the day starts at 08:00 and each turn is 10 s. */
export function wallClock(turn: number): string {
  const mins = Math.floor((8 * 3600 + turn * RUN.secPerStep) / 60);
  const h = String(Math.floor(mins / 60)).padStart(2, "0");
  return `${h}:${String(mins % 60).padStart(2, "0")}`;
}

/**
 * The day's highlights, in step order — where to scrub to in the demo above
 * (steps are the demo timeline's own unit). Adapted from PR #955 (@0frankie);
 * each row is re-verified against the replay's event log and transcripts, and
 * the test pins the ordering, bounds, and clock strings.
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
  {
    step: 537,
    moment:
      "Mateo finds Tanaka in Irvine, buzzing about the lecture and checking everything's ready.",
  },
  {
    step: 705,
    moment:
      "The gravitational-waves lecture begins: Tanaka front and center, Mateo running the AV booth.",
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
  { step: 4026, moment: "Mateo winds down the day walking with his sister Elena at College Hall." },
];

/**
 * A displayed dialogue line. `fragments` are each a contiguous verbatim
 * substring of ONE transcript line by `speaker`; the renderer joins them with
 * an ellipsis where the original ran longer.
 */
export interface DialogLine {
  speaker: string;
  fragments: string[];
}

export interface Dialog {
  place: string;
  /** Turn of the conversation's last line — the transcript is complete here. */
  endTurn: number;
  participants: [string, string];
  lines: DialogLine[];
}

export const DIALOGS: Record<"sandwich" | "lecture" | "whiteboard", Dialog> = {
  sandwich: {
    place: "Van Pelt — Moelis Reading Room",
    endTurn: 2123,
    participants: ["Maya Chen", "Theo Lindqvist"],
    lines: [
      {
        speaker: "Maya Chen",
        fragments: [
          "*looks up from laptop with a tired but genuine smile* Theo! Still burning the midnight oil, I see. Fair warning: I'm on my third coffee of the evening, so my conversation skills might be a little... caffeinated.",
        ],
      },
      {
        speaker: "Theo Lindqvist",
        fragments: [
          "But seriously, good luck tomorrow; want to grab actual food after your exam? I owe you for keeping me sane at this hour.",
        ],
      },
      {
        speaker: "Maya Chen",
        fragments: [
          "You know what? I would love that.",
          "There's this place near campus that has really good sandwiches, if you're into that?",
        ],
      },
      {
        speaker: "Theo Lindqvist",
        fragments: [
          "Sandwiches sound perfect—honestly, at this point I'd probably eat a sandwich that Kant wrote a categorical imperative about.",
          "Just text me when you're done and we'll hunt down those sandwiches.",
        ],
      },
    ],
  },
  lecture: {
    place: "Irvine Auditorium",
    endTurn: 634,
    participants: ["Professor Tanaka", "Mateo Vasquez"],
    lines: [
      {
        speaker: "Professor Tanaka",
        fragments: [
          "Mateo—good to see you here and ready. The equipment you confirmed is holding up beautifully. How are you feeling about the lecture?",
        ],
      },
      {
        speaker: "Mateo Vasquez",
        fragments: [
          "Thanks, Professor—I'm really excited! Honestly, I'm a little nervous about managing the tech during the live data segments, but seeing it all come together like this makes it worth it.",
        ],
      },
      {
        speaker: "Professor Tanaka",
        fragments: [
          "That nervousness is a good sign—it means you care about getting it right. You've got this, Mateo.",
          "if anything does go sideways, we'll handle it together.",
        ],
      },
    ],
  },
  whiteboard: {
    place: "Irvine Auditorium",
    endTurn: 1442,
    participants: ["Priya Nair", "Professor Tanaka"],
    lines: [
      {
        speaker: "Priya Nair",
        fragments: [
          "I understand the concept of correlating the incoming signal with a template, but I got confused about *why* that specifically maximizes the signal-to-noise ratio",
        ],
      },
      {
        speaker: "Professor Tanaka",
        fragments: [
          "Ah, excellent question—that's where the real elegance lies! Let me grab a marker and sketch this out for you; it comes down to the Cauchy-Schwarz inequality",
        ],
      },
      {
        speaker: "Priya Nair",
        fragments: [
          "Okay, that makes so much sense—I think I was missing that connection to Cauchy-Schwarz.",
          "Can you sketch it out? I think seeing it would help me lock it in.",
        ],
      },
      {
        speaker: "Professor Tanaka",
        fragments: [
          "*picks up a marker and turns to the nearest board with a slight smile* Absolutely—let me draw this out for you.",
        ],
      },
    ],
  },
};

/**
 * A quoted memory record. `text` is a contiguous verbatim substring of the
 * record's full text (usually the whole thing).
 */
export interface MemoryQuote {
  agent: string;
  turn: number;
  kind: "plan" | "reflection" | "chat" | "observation";
  importance: number;
  text: string;
}

/** The sandwich pact, as written into BOTH participants' memory streams. */
export const PLAN_TWINS: MemoryQuote[] = [
  {
    agent: "Maya Chen",
    turn: 2123,
    kind: "plan",
    importance: 8,
    text: "I agreed with Theo Lindqvist: Grab sandwiches with Theo at a place near campus after my biology exam tomorrow; I'll text him when I'm done.",
  },
  {
    agent: "Theo Lindqvist",
    turn: 2123,
    kind: "plan",
    importance: 8,
    text: "I agreed with Maya Chen: Grab sandwiches with Maya Chen at the place near campus after her exam tomorrow; she'll text when she's done.",
  },
];

/** Maya's complete plan-memory trail: one initial plan, seven commitments. */
export const MAYA_TIMELINE: MemoryQuote[] = [
  {
    agent: "Maya Chen",
    turn: 0,
    kind: "plan",
    importance: 5,
    text: "Plan: go to Van Pelt — Circulation Desk and checking out a reserved organic chemistry textbook.",
  },
  {
    agent: "Maya Chen",
    turn: 5,
    kind: "plan",
    importance: 8,
    text: "I agreed with Priya Nair: Head to Van Pelt circulation with Priya to get the organic chem textbook, then grab coffee, then study together in Moelis Reading Room for problem sets.",
  },
  {
    agent: "Maya Chen",
    turn: 204,
    kind: "plan",
    importance: 8,
    text: "I agreed with Priya Nair: Get the organic chemistry textbook from the circulation desk, then grab cold brew coffee at a spot off campus with Priya, and afterward settle in at Moelis to work through problem sets together.",
  },
  {
    agent: "Maya Chen",
    turn: 488,
    kind: "plan",
    importance: 8,
    text: "I agreed with Priya Nair: Grab coffee off-campus and return in about fifteen minutes to meet Priya at a table in the library to work on problem sets together.",
  },
  {
    agent: "Maya Chen",
    turn: 763,
    kind: "plan",
    importance: 8,
    text: "I agreed with Priya Nair: Study Chapter 5 mechanisms with Priya, starting with problem 3, focusing on electron-pushing mechanisms for the midterm",
  },
  {
    agent: "Maya Chen",
    turn: 2123,
    kind: "plan",
    importance: 8,
    text: "I agreed with Theo Lindqvist: Grab sandwiches with Theo at a place near campus after my biology exam tomorrow; I'll text him when I'm done.",
  },
  {
    agent: "Maya Chen",
    turn: 2305,
    kind: "plan",
    importance: 8,
    text: "I agreed with Theo Lindqvist: Head home to sleep before the exam, then text Theo once the exam is finished",
  },
  {
    agent: "Maya Chen",
    turn: 4239,
    kind: "plan",
    importance: 8,
    text: "I agreed with Theo Lindqvist: Heading back to sleep now after a long library day, ending study session",
  },
];

/** Observation → distilled chat memory → reflection → prediction, one thread. */
export const MEMORY_CHAIN: MemoryQuote[] = [
  {
    agent: "Professor Tanaka",
    turn: 540,
    kind: "chat",
    importance: 8,
    text: "Mateo Vasquez is an AV tech (likely a student) at Penn who is genuinely enthusiastic about physics, especially gravitational waves/LIGO. He's reliable—confirmed the projector and sound system are tested and working for the 10:00 gravitational waves lecture. Worth encouraging his interest in physics.",
  },
  {
    agent: "Professor Tanaka",
    turn: 597,
    kind: "reflection",
    importance: 6,
    text: "There is a genuine opportunity to mentor Mateo further, given his confirmed enthusiasm for physics and reliable AV work, which was explicitly noted as worth encouraging.",
  },
  {
    agent: "Professor Tanaka",
    turn: 705,
    kind: "reflection",
    importance: 6,
    text: "likely next mentorship steps would include following up with Mateo after the Q&A",
  },
];

export const THEO_REFLECTIONS: MemoryQuote[] = [
  {
    agent: "Theo Lindqvist",
    turn: 1241,
    kind: "reflection",
    importance: 6,
    text: "Despite self-describing as useless before noon, I recommended a 10am lecture and am now heading to an impromptu coffee meetup shortly after—showing I prioritize relationships and intellectual curiosity (especially fostering Mateo's engagement with determinism) over strictly honoring my own night-owl rhythm, even though follow-through on the meetup itself remains unconfirmed.",
  },
  {
    agent: "Theo Lindqvist",
    turn: 1913,
    kind: "reflection",
    importance: 6,
    text: "we planned to meet at Van Pelt Library to discuss determinism, and Mateo has independently continued these discussions with Theo Lindqvist",
  },
];

/** The engine refusing a repeat conversation, as the agent experienced it. */
export const COOLDOWN_OBS: MemoryQuote = {
  agent: "Professor Tanaka",
  turn: 597,
  kind: "observation",
  importance: 3,
  text: "I tried to \"talk_to Mateo Vasquez about confirming av setup is ready and thanking him before the lecture starts\" but it didn't work: we have talked recently, and it's too soon to talk again.",
};

export const MATEO_AMNESIA: MemoryQuote = {
  agent: "Mateo Vasquez",
  turn: 1061,
  kind: "plan",
  importance: 8,
  text: "I agreed with Theo Lindqvist: Check out the gravitational waves lecture at Irvine at 10, and report back to Theo what I think",
};

/**
 * Dialogue lines quoted in the verdict prose. `agent` names the transcript
 * the line is pinned in (a conversation appears in both participants'
 * transcripts); `speaker` said it; `fragment` is a contiguous verbatim
 * substring of the line at `turn`.
 */
export const QUOTED_LINES: { agent: string; turn: number; speaker: string; fragment: string }[] = [
  {
    agent: "Priya Nair",
    turn: 484,
    speaker: "Priya Nair",
    fragment: "Already got my cold brew from the off-campus spot! I'm all set.",
  },
  {
    agent: "Maya Chen",
    turn: 758,
    speaker: "Maya Chen",
    fragment: "Okay, I'm back! Got the coffee and everything.",
  },
  {
    agent: "Priya Nair",
    turn: 1033,
    speaker: "Maya Chen",
    fragment: "I'm officially caffeinated now—grabbed a cold brew on the way in.",
  },
  {
    agent: "Theo Lindqvist",
    turn: 2023,
    speaker: "Theo Lindqvist",
    fragment: "What brings you to the Moelis at this hour?",
  },
  {
    agent: "Theo Lindqvist",
    turn: 3580,
    speaker: "Theo Lindqvist",
    fragment: "Plus, it's like 11 PM, which means your brain is finally waking up anyway, right?",
  },
  {
    agent: "Maya Chen",
    turn: 3963,
    speaker: "Maya Chen",
    fragment: "My exam's Friday, so I've still got two days to pull myself together",
  },
  {
    agent: "Maya Chen",
    turn: 4319,
    speaker: "Maya Chen",
    fragment: "Got a B+, which I'll take given how much that exam stressed me out.",
  },
  {
    agent: "Mateo Vasquez",
    turn: 1061,
    speaker: "Mateo Vasquez",
    fragment:
      "Gravitational waves sounds pretty cool—I'll definitely look into that, thanks for the tip!",
  },
  {
    agent: "Mateo Vasquez",
    turn: 1152,
    speaker: "Mateo Vasquez",
    fragment: "Yeah, I did make it! Honestly, it was pretty mind-bending",
  },
  {
    agent: "Mateo Vasquez",
    turn: 819,
    speaker: "Mateo Vasquez",
    fragment: "moments like this make it feel like I'm exactly where I'm supposed to be",
  },
  {
    agent: "Theo Lindqvist",
    turn: 4319,
    speaker: "Maya Chen",
    fragment:
      "How's the Foucault paper coming along—did you actually start it, or are we still in denial mode?",
  },
  {
    agent: "Theo Lindqvist",
    turn: 4319,
    speaker: "Theo Lindqvist",
    fragment: "I'm about two thousand words in",
  },
  {
    agent: "Maya Chen",
    turn: 4319,
    speaker: "Maya Chen",
    fragment: "I've been here since like 8 AM and my brain is basically pudding at this point.",
  },
];

/**
 * Mean scores from the run's LLM believability audit
 * (runs/issue-760-batch-12/runA/believability.md), hand-copied and pinned in
 * CaseStudySection.test.ts the way CostSection pins its CSV.
 */
export const JUDGE = {
  planCoherence: 6.1,
  temporalSanity: 6.04,
  socialGrounding: 8.04,
  worldGrounding: 9.6,
  memoryUse: 7.12,
  overall: 7.38,
  weakestAgent: "Mateo Vasquez",
  weakestScore: 5.4,
};

/** Italicize *stage directions* the way the transcript marks them. */
function withStageDirections(text: string) {
  let offset = 0;
  return text.split(/(\*[^*]+\*)/g).map((part) => {
    const key = offset;
    offset += part.length;
    return part.startsWith("*") && part.endsWith("*") && part.length > 2 ? (
      <em key={key}>{part.slice(1, -1)}</em>
    ) : (
      <span key={key}>{part}</span>
    );
  });
}

function DialogFigure({ dialog }: { dialog: Dialog }) {
  return (
    <figure className="nrf-dialog">
      <figcaption className="nrf-dialog-meta">
        {dialog.participants[0]} and {dialog.participants[1]} — {dialog.place}, around{" "}
        {wallClock(dialog.endTurn)} (turn {dialog.endTurn})
      </figcaption>
      {dialog.lines.map((line) => (
        <p key={line.fragments[0]}>
          <strong>{line.speaker.split(" ")[0]}:</strong>{" "}
          {line.fragments.map((f) => (
            <span key={f}>
              {f !== line.fragments[0] && <span> […] </span>}
              {withStageDirections(f)}
            </span>
          ))}
        </p>
      ))}
    </figure>
  );
}

function MemoryCard({ memory }: { memory: MemoryQuote }) {
  return (
    <div className="nrf-memcard">
      <span className="nrf-memmeta">
        <span className="nrf-memkind">{memory.kind}</span>
        {memory.agent}, turn {memory.turn} ({wallClock(memory.turn)}) — importance{" "}
        {memory.importance.toFixed(1)}
      </span>
      <p>{memory.text}</p>
    </div>
  );
}

/**
 * The #878 selected-run case study: the one day of simulation the demo at the
 * top of the page plays back, read beat by beat before the architecture that
 * produced it.
 */
export function CaseStudySection() {
  return (
    <section className="nrf-section">
      <div className="nrf-container">
        <div className="nrf-narrow">
          <SectionHeading id="case-study" level={2} className="nrf-title nrf-title-3 nrf-centered">
            One simulated day, up close
          </SectionHeading>
          <div className="nrf-content nrf-justified">
            <p>
              The replay above is one specific run — a single simulated Monday from 08:00 to 20:00,
              4,320 ticks of ten simulated seconds each, with five agents, plans authored by{" "}
              <code>{RUN.planModel}</code> and dialogue, scoring, and reactions by{" "}
              <code>{RUN.liveModel}</code>. The day produced {RUN.events} gate-approved actions and{" "}
              {RUN.conversations} conversations, and cost ${RUN.costUsd.toFixed(2)} — the five-agent
              baseline in the cost section below. This section walks that day beat by beat; the next
              section is the machinery behind each moment. Every quotation that follows is copied
              verbatim from the replay file the demo plays.
            </p>

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
                    <td>{wallClock(step)}</td>
                    <td>{step.toLocaleString()}</td>
                    <td>{moment}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <SectionHeading id="case-cast" level={3} className="nrf-title nrf-title-4">
              The cast and their mornings
            </SectionHeading>
            <p>
              At 08:00 each agent wrote its own day: the planner turned a one-paragraph persona into
              a morning-to-evening outline, then into concrete stops on the real map. The five
              intents, in the planner's own words:
            </p>
            <ul>
              <li>
                <strong>Professor Tanaka</strong> 🔬 — "Arrive at Irvine Auditorium early to set up
                for the 10:00 guest lecture on gravitational waves — check AV equipment, test the
                projector and mic," then a problem session at Williams Hall.
              </li>
              <li>
                <strong>Maya Chen</strong> 📚 (biology sophomore, "a little caffeine-dependent") —
                "Start at Van Pelt Circulation Desk to check out the reserved organic chemistry
                textbook, then meet Priya Nair for our usual morning study session… Grab caffeine as
                needed along the way."
              </li>
              <li>
                <strong>Priya Nair</strong> 💻 (CS junior) — "Meet Maya at Van Pelt — Moelis Reading
                Room around 8:00 to grind through the problem set before class."
              </li>
              <li>
                <strong>Theo Lindqvist</strong> 🦉 (philosophy junior) — "Slow start, true to
                philosopher's hours… forgo the early gravitational waves lecture (sorry, Professor
                Tanaka) and surface properly at Houston Hall for a long, unhurried brunch. Coffee
                first, opinions second."
              </li>
              <li>
                <strong>Mateo Vasquez</strong> 🐣 (first-year) — "Meet up with Elena early and head
                to College Hall, trailing her around as she shows me the ropes." Elena, his older
                sister, exists only in his persona text — she is not one of the five simulated
                agents, a detail that matters later.
              </li>
            </ul>

            <SectionHeading id="case-dialogs" level={3} className="nrf-title nrf-title-4">
              Three conversations
            </SectionHeading>
            <p>
              Conversations start when two agents are adjacent, free, and mutually interested, and
              unfold one line per tick; when one ends, each participant distills what was agreed
              into memory. One of the run's most consequential exchanges is also its most ordinary:
              at 13:53, deep in the reading room, Maya and Theo drift from Kant and the Krebs cycle
              into making a plan.
            </p>
            <DialogFigure dialog={DIALOGS.sandwich} />
            <p>
              The exchange itself is disposable small talk. What makes it architecture is the next
              tick: the conversation's outcome pass writes a commitment into <em>both</em> memory
              streams, with the fixed importance a commitment carries, phrased from each side's own
              point of view.
            </p>
            {PLAN_TWINS.map((m) => (
              <MemoryCard key={m.agent} memory={m} />
            ))}
            <p>
              Earlier that morning the same machinery carried a different register. At 09:45, five
              minutes before the guest lecture, the professor found his student AV tech at the
              booth:
            </p>
            <DialogFigure dialog={DIALOGS.lecture} />
            <p>
              And just before noon, Priya cornered Tanaka after the lecture to ask why matched
              filtering maximizes signal-to-noise. The model plays both roles — the student's
              half-understanding and the professor's marker-in-hand enthusiasm — and the physics is
              real:
            </p>
            <DialogFigure dialog={DIALOGS.whiteboard} />
            <p>
              That last exchange ends with Priya committing to stay and watch the derivation —
              "Staying to watch Professor Tanaka sketch out the Cauchy-Schwarz/matched filtering
              derivation on the board right now" — which quietly displaces the solo afternoon her
              own plan had scheduled. Curiosity overriding a schedule is exactly the failure mode a
              scripted NPC cannot have.
            </p>

            <SectionHeading id="case-goals" level={3} className="nrf-title nrf-title-4">
              A day of changing plans
            </SectionHeading>
            <p>
              Plans are living documents
              <CodeRef>
                <code>maybe_revise_plan()</code>, in <code>backend/cognition.py</code>
              </CodeRef>{" "}
              and Maya's memory stream keeps the whole edit history: one initial plan and seven
              commitments, every one of them social. Her 08:00 plan named six stops — circulation
              desk, Moelis study session, coffee at Houston Hall, a College Hall seminar, the book
              stacks, the study booths:
            </p>
            <ol className="nrf-timeline">
              {MAYA_TIMELINE.map((m) => (
                <li key={m.turn}>
                  <span className="nrf-time">{wallClock(m.turn)}</span>
                  {m.text}
                </li>
              ))}
            </ol>
            <p>
              Held against her actual event log, the trail splits cleanly in two. The social
              commitments are kept: she studies electron-pushing mechanisms with Priya from 10:26 to
              just past 12:26 — problem 3 first, as agreed at 10:07 — sits the seminar from 15:44,
              and ends the day exactly as the sandwich pact requires, telling Theo she is heading
              home at 19:46. The logistical ones dissolve: no coffee-buying action ever fires all
              day (more on that below), and the 14:24 resolution to "head home to sleep before the
              exam" is followed, seven minutes later, by her walking to Houston Hall and then
              carrying on with the original schedule — seminar, stacks, study booths — for five more
              hours. Along the way she checks out a campus history book at 18:55 that no plan ever
              mentioned. The believability audit scores this dimension harshly (plan coherence{" "}
              {JUDGE.planCoherence}/10 across the cast), but the <em>shape</em> of the failure is
              oddly human: promises to other people hold; promises to oneself about sleep do not.
            </p>

            <SectionHeading id="case-memory" level={3} className="nrf-title nrf-title-4">
              Memory at work
            </SectionHeading>
            <p>
              The memory stream is not a log; it condenses. Here is one thread of Tanaka's morning,
              three records deep. After a pre-lecture chat with Mateo at 09:30, the outcome pass
              stores not the transcript but a judgement; a reflection at 09:39 distills several such
              records into a conclusion; and a second reflection at 09:57 extrapolates it forward:
            </p>
            {MEMORY_CHAIN.map((m) => (
              <MemoryCard key={m.turn} memory={m} />
            ))}
            <p>
              The prediction comes true: just after the Q&amp;A, at 10:15, Tanaka seeks Mateo out
              again ("You did more than manage the tech today"), and Mateo's reply — "moments like
              this make it feel like I'm exactly where I'm supposed to be" — is the run's best line,
              delivered by its weakest agent. Reflection can also turn inward. Theo, at 11:26,
              catches his own behavior contradicting his persona:
            </p>
            <MemoryCard memory={THEO_REFLECTIONS[0]} />
            <p>
              That is retrieval doing real work: the persona's "useless before noon" and the
              morning's actual choices are only in tension if both are on the table at once. The
              same mechanism has a tell, though — at 13:18 Theo reflects that "Mateo has
              independently continued these discussions with Theo Lindqvist," referring to himself
              in the third person, a seam where the narrator's view leaks into the agent's.
            </p>

            <SectionHeading id="case-verdict" level={3} className="nrf-title nrf-title-4">
              What holds up, and what gives it away
            </SectionHeading>
            <p>
              An LLM judge audited the run agent by agent, with step-ranged evidence for every
              score. The mean scores:
            </p>
            <table className="nrf-scores">
              <tbody>
                <tr>
                  <td>World grounding</td>
                  <td>{JUDGE.worldGrounding}/10</td>
                </tr>
                <tr>
                  <td>Social grounding</td>
                  <td>{JUDGE.socialGrounding}/10</td>
                </tr>
                <tr>
                  <td>Memory use</td>
                  <td>{JUDGE.memoryUse}/10</td>
                </tr>
                <tr>
                  <td>Plan coherence</td>
                  <td>{JUDGE.planCoherence}/10</td>
                </tr>
                <tr>
                  <td>Temporal sanity</td>
                  <td>{JUDGE.temporalSanity}/10</td>
                </tr>
                <tr>
                  <td>
                    <strong>Overall</strong>
                  </td>
                  <td>
                    <strong>{JUDGE.overall}/10</strong>
                  </td>
                </tr>
              </tbody>
            </table>
            <p>
              <strong>What reads as real.</strong> The Tanaka–Mateo mentorship arc spans three
              escalating conversations in one morning — equipment check, pre-lecture nerves,
              post-lecture pride — with matching memories on both sides; the judge found "no
              confabulation detected" in either stream. Theo's whole day is a legible deviation: he
              planned to skip the lecture, met Mateo over brunch instead, got pulled into
              determinism versus the measurement problem, and committed at 11:12 to an unplanned
              coffee meetup at Van Pelt — the judge explicitly credited that the reason for the
              detour is visible in the record. And the day has long-range continuity: a Foucault
              paper Theo mentions just before 19:00 gets called back at 19:45 ("did you actually
              start it, or are we still in denial mode?" — "I'm about two thousand words in"), and
              Maya's last-conversation aside that "I've been here since like 8 AM and my brain is
              basically pudding" is, per the event log, exactly true. Even the engine's plumbing can
              read as manners: when Tanaka tries to thank Mateo twice in ten minutes, the
              conversation cooldown refuses, and the refusal lands in his memory like social
              instinct —
            </p>
            <MemoryCard memory={COOLDOWN_OBS} />
            <p>
              <strong>What gives it away.</strong> The failures cluster where generation is only
              softly grounded. The clearest is the phantom coffee: Maya and Priya's agreed
              off-campus cold-brew run never happens — no travel, no purchase, nothing in the event
              log — yet both narrate it as done, three separate times ("Already got my cold brew
              from the off-campus spot!" at 09:20; "Okay, I'm back! Got the coffee and everything"
              at 10:06; "grabbed a cold brew on the way in" at 10:52). The judge's verdict: "This is
              a confabulation." Second, the dialogue model is clock-blind: the sandwich pact above —
              a 13:53 conversation — opens with "burning the midnight oil" and "my third coffee of
              the evening," Theo wonders what brings Maya to the reading room "at this hour" at
              13:37, and at 17:56 he asserts "it's like 11 PM." Maya's exam drifts the same way:
              "tomorrow" at 13:53, already taken by 17:55, "My exam's Friday" at 19:00, and a B+ in
              hand by 19:45 — four mutually impossible timelines in six hours. Third, and strangest:
              Mateo spends the morning running the AV booth for the gravitational waves lecture,
              then within the hour tells Theo "Gravitational waves sounds pretty cool—I'll
              definitely look into that, thanks for the tip!" and commits to attend the lecture he
              has already worked —
            </p>
            <MemoryCard memory={MATEO_AMNESIA} />
            <p>
              — sixteen minutes later reporting back "Yeah, I did make it!" The judge scored his
              temporal sanity 2/10 and made him the run's weakest agent at {JUDGE.weakestScore}/10;
              he also ends the day performing "walking with Elena," the sister who exists only in
              his backstory. Two smaller tells: the wish channel — meant to catch desires the world
              cannot satisfy — logged sixteen entries this run, every one a parser fragment like
              "problem 3" or "or just head to moelis?" rather than a real unmet want; and Theo wrote
              twelve reflections to his castmates' 21–27, so the agent with the richest persona
              voice has the thinnest inner life on record.
            </p>
            <p>
              The pattern across all of it is one line: the scores are high exactly where the engine
              holds the pen and low where the model does. Locations, actions, and inventory are
              precondition-gated, so world grounding sits at {JUDGE.worldGrounding}/10; dialogue
              content and its sense of time are generated free-hand, so temporal sanity sits at{" "}
              {JUDGE.temporalSanity}/10. The gate can stop an agent from drinking a coffee that does
              not exist. It cannot yet stop her from telling a friend she already drank it.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
