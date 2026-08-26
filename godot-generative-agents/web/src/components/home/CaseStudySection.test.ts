import { describe, expect, it } from "vitest";
// Every quotation in the case study — dialogue lines, plan memories,
// reflections — must be a verbatim excerpt of the bundled showcase replay, the
// same file the demo plays. Import it raw (a typed JSON import this size would
// make tsc materialize a 3.7 MB literal type) and pin each exported constant
// to the record it quotes. Judge numbers have no machine-readable source in
// the web bundle, so they are hand-copied literals here, the way
// CostSection.test.ts pins its CSV.
import replayRaw from "../../../public/replay/penn_replay.json?raw";
import { fattenFrames } from "../../replayCodec";
import type { Replay } from "../../types/replay";
import {
  COOLDOWN_OBS,
  DIALOGS,
  HIGHLIGHTS,
  JUDGE,
  MATEO_AMNESIA,
  MAYA_TIMELINE,
  MEMORY_CHAIN,
  type MemoryQuote,
  PLAN_TWINS,
  QUOTED_LINES,
  RUN,
  THEO_REFLECTIONS,
  wallClock,
} from "./CaseStudySection";
import { BASELINE_REPLICATES } from "./CostSection";

const replay = JSON.parse(replayRaw) as Replay;
const frames = fattenFrames(replay.frames);
const streams = replay.memory_streams ?? {};
const events = replay.events ?? [];

/** The full conversation transcript an agent's frame carries at `turn`. */
function transcriptAt(agent: string, turn: number): [string, string][] {
  return frames[turn]?.[agent]?.chat ?? [];
}

function expectMemory(quote: MemoryQuote) {
  const match = (streams[quote.agent] ?? []).find(
    (m) => m.kind === quote.kind && m.created_turn === quote.turn && m.text.includes(quote.text),
  );
  expect(
    match,
    `${quote.agent} t${quote.turn} ${quote.kind}: "${quote.text.slice(0, 60)}…"`,
  ).toBeDefined();
  expect(match?.importance).toBe(quote.importance);
}

describe("the run's provenance", () => {
  it("matches the replay meta", () => {
    // The showcase file's meta carries provenance fields (#845) beyond the
    // baked-replay type, hence the widening.
    const meta = replay.meta as typeof replay.meta & Record<string, unknown>;
    expect(meta.seed).toBe(RUN.seed);
    expect(meta.engine_sha).toBe(RUN.engineSha);
    expect(meta.num_steps).toBe(RUN.steps);
    expect(meta.sec_per_step).toBe(RUN.secPerStep);
    expect(meta.start).toBe(RUN.start);
    expect(meta.plan_mode).toBe(RUN.planMode);
    const llm = meta.llm as unknown as { model: string; models: Record<string, string> };
    expect(llm.model).toBe(RUN.planModel);
    expect(llm.models.converse).toBe(RUN.liveModel);
    expect(replay.frames).toHaveLength(RUN.steps);
    expect(replay.events).toHaveLength(RUN.events);
  });

  it("quotes the same cost as the cost section's baseline", () => {
    expect(RUN.costUsd).toBe(BASELINE_REPLICATES[0]);
  });

  it("converts turns to the sim wall clock", () => {
    expect(wallClock(0)).toBe("08:00");
    expect(wallClock(2123)).toBe("13:53");
    expect(wallClock(4319)).toBe("19:59");
  });
});

describe("the dialogue excerpts", () => {
  const cases = Object.entries(DIALOGS).flatMap(([name, dialog]) =>
    dialog.lines.map((line) => [name, dialog, line] as const),
  );

  it.each(
    cases,
  )("%s: every fragment is verbatim from one transcript line", (_name, dialog, line) => {
    const transcript = transcriptAt(dialog.participants[0], dialog.endTurn);
    const hit = transcript.find(
      ([speaker, text]) =>
        speaker === line.speaker && line.fragments.every((f) => text.includes(f)),
    );
    expect(hit, `${line.speaker}: "${line.fragments[0].slice(0, 60)}…"`).toBeDefined();
  });

  it.each(QUOTED_LINES)("prose quote at turn $turn is verbatim from $agent's transcript", ({
    agent,
    turn,
    speaker,
    fragment,
  }) => {
    const hit = transcriptAt(agent, turn).find(
      ([sp, text]) => sp === speaker && text.includes(fragment),
    );
    expect(hit, `"${fragment.slice(0, 60)}…"`).toBeDefined();
  });
});

describe("the scrub-to highlights", () => {
  it("lists moments in step order, within the day", () => {
    const steps = HIGHLIGHTS.map((h) => h.step);
    expect(steps).toEqual([...steps].sort((a, b) => a - b));
    expect(steps[0]).toBe(0);
    expect(steps[steps.length - 1]).toBeLessThan(RUN.steps);
  });

  it("anchors every row to the replay", () => {
    // Two rows point at conversation moments (no event on that exact turn);
    // pin those to the transcript lines they describe. Every other row must
    // have a logged event at exactly its step.
    const eventTurns = new Set(events.map((e) => e.turn));
    const chatPins: Record<number, [string, string]> = {
      814: ["Professor Tanaka", "live LIGO data was seamless"],
      1151: ["Theo Lindqvist", "make it to that gravitational waves lecture"],
    };
    for (const { step } of HIGHLIGHTS) {
      const pin = chatPins[step];
      if (pin) {
        const [agent, fragment] = pin;
        expect(
          transcriptAt(agent, step).some(([, text]) => text.includes(fragment)),
          `t${step}: "${fragment}"`,
        ).toBe(true);
      } else {
        expect(eventTurns.has(step), `no event at t${step}`).toBe(true);
      }
    }
    // The one quoted fragment in a moment cell is verbatim from its event.
    expect(
      events.some((e) => e.turn === 3573 && e.summary.includes("funny running into you")),
    ).toBe(true);
  });
});

describe("the memory quotes", () => {
  const quotes = [
    ...PLAN_TWINS,
    ...MAYA_TIMELINE,
    ...MEMORY_CHAIN,
    ...THEO_REFLECTIONS,
    COOLDOWN_OBS,
    MATEO_AMNESIA,
  ];

  it.each(quotes)("$agent's $kind at turn $turn is a verbatim record", (quote) => {
    expectMemory(quote);
  });

  it("Maya's timeline is her complete plan-kind stream", () => {
    const plans = (streams["Maya Chen"] ?? []).filter((m) => m.kind === "plan");
    expect(plans.map((m) => m.created_turn)).toEqual(MAYA_TIMELINE.map((m) => m.turn));
  });
});

describe("the judge scores", () => {
  it("match the believability audit", () => {
    // Hand-copied from runs/issue-760-batch-12/runA/believability.md ("Run
    // summary" table). If the audit is re-run, update both.
    expect(JUDGE).toEqual({
      planCoherence: 6.1,
      temporalSanity: 6.04,
      socialGrounding: 8.04,
      worldGrounding: 9.6,
      memoryUse: 7.12,
      overall: 7.38,
      weakestAgent: "Mateo Vasquez",
      weakestScore: 5.4,
    });
  });
});
