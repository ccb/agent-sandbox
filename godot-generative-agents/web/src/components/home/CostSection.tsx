/**
 * "What a day costs" — the cost-scaling measurements of issue #921, charted.
 *
 * Every number here is pinned to godot-generative-agents/runs/cost-scaling/
 * cost_scaling.csv (one row per run; canonical cost = the run's usage.json
 * total_cost_usd). All runs share the showcase recipe: seed 42, effort medium,
 * Sonnet 5 on decide/plan/reflect/outcome and Haiku 4.5 on converse/score/
 * react, cognition tools on unless stated. CostSection.test.ts pins these
 * constants against the CSV's values so the prose and the data can't drift
 * apart. A `cost: null` would mark a not-yet-measured cell (its point/panel
 * stays hidden); as of 2026-08-01 every cell is measured.
 */

import { SectionHeading } from "./SectionHeading";

/** The three 5-agent / 12-hour replicates (batches 12, 10, 11 of #760). */
export const BASELINE_REPLICATES = [5.37355, 5.381057, 6.818001];

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

export const BASELINE = {
  cost: mean(BASELINE_REPLICATES),
  lo: Math.min(...BASELINE_REPLICATES),
  hi: Math.max(...BASELINE_REPLICATES),
};

/** One measured point: x is the swept variable, lo/hi an optional range bar. */
export type CostPoint = {
  x: number;
  cost: number | null;
  lo?: number;
  hi?: number;
};

/** Cost vs cast size, at 12 simulated hours. */
export const AGENT_POINTS: CostPoint[] = [
  { x: 1, cost: 0.518008 },
  { x: 3, cost: 3.157274 },
  { x: 5, ...BASELINE },
  { x: 7, cost: 8.574769 },
];

/** Cost vs simulated hours, at 5 agents. */
export const DURATION_POINTS: CostPoint[] = [
  { x: 3, cost: 1.377269 },
  { x: 6, cost: 2.957218 },
  { x: 12, ...BASELINE },
];

/** Cognition tools on vs off, at 5 agents / 12 hours. */
export const COGNITION_BARS: { label: string; cost: number | null; lo?: number; hi?: number }[] = [
  { label: "tools on", ...BASELINE },
  { label: "tools off", cost: 7.070765 },
];

/** Smallest "nice" value ≥ v, for a y-axis that ends on a round number. */
export function niceMax(v: number): number {
  const pow = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8]) {
    if (m * pow >= v) return m * pow;
  }
  return 10 * pow;
}

const usd = (v: number) => `$${v.toFixed(2)}`;

// One shared geometry for every panel, so they read as a set.
const W = 320;
const H = 210;
const PLOT = { left: 42, right: 308, top: 14, bottom: 168 };

function scales(points: { cost: number | null; hi?: number }[], maxX: number) {
  const costs = points.flatMap((p) => (p.cost === null ? [] : [p.hi ?? p.cost]));
  const maxY = niceMax(Math.max(...costs));
  return {
    maxY,
    px: (x: number) => PLOT.left + (x / maxX) * (PLOT.right - PLOT.left),
    py: (c: number) => PLOT.bottom - (c / maxY) * (PLOT.bottom - PLOT.top),
  };
}

/** Axes + y ticks at 0 / half / max — shared by both chart shapes. */
function Axes({ maxY, py }: { maxY: number; py: (c: number) => number }) {
  return (
    <g className="nrf-chart-axis">
      <line x1={PLOT.left} y1={PLOT.top} x2={PLOT.left} y2={PLOT.bottom} />
      <line x1={PLOT.left} y1={PLOT.bottom} x2={PLOT.right} y2={PLOT.bottom} />
      {[0, maxY / 2, maxY].map((tick) => (
        <text key={tick} x={PLOT.left - 5} y={py(tick) + 3} textAnchor="end">
          {usd(tick)}
        </text>
      ))}
    </g>
  );
}

function RangeBar({
  x,
  lo,
  hi,
  py,
}: {
  x: number;
  lo: number;
  hi: number;
  py: (c: number) => number;
}) {
  return (
    <g className="nrf-chart-range">
      <line x1={x} y1={py(lo)} x2={x} y2={py(hi)} />
      <line x1={x - 4} y1={py(lo)} x2={x + 4} y2={py(lo)} />
      <line x1={x - 4} y1={py(hi)} x2={x + 4} y2={py(hi)} />
    </g>
  );
}

function LineChart({
  points,
  xLabel,
  caption,
  ariaLabel,
}: {
  points: CostPoint[];
  xLabel: string;
  caption: string;
  ariaLabel: string;
}) {
  const shown = points.filter((p): p is CostPoint & { cost: number } => p.cost !== null);
  const maxX = Math.max(...shown.map((p) => p.x));
  const { maxY, px, py } = scales(shown, maxX);
  const path = shown.map((p, i) => `${i === 0 ? "M" : "L"}${px(p.x)},${py(p.cost)}`).join(" ");
  return (
    <figure className="nrf-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel}>
        <Axes maxY={maxY} py={py} />
        <text
          className="nrf-chart-xlabel"
          x={(PLOT.left + PLOT.right) / 2}
          y={H - 4}
          textAnchor="middle"
        >
          {xLabel}
        </text>
        <path className="nrf-chart-line" d={path} fill="none" />
        {shown.map((p) => (
          <g key={p.x}>
            {p.lo !== undefined && p.hi !== undefined && (
              <RangeBar x={px(p.x)} lo={p.lo} hi={p.hi} py={py} />
            )}
            <circle className="nrf-chart-dot" cx={px(p.x)} cy={py(p.cost)} r={3.5} />
            <text
              className="nrf-chart-value"
              x={px(p.x)}
              y={py(p.hi ?? p.cost) - 7}
              textAnchor="middle"
            >
              {usd(p.cost)}
            </text>
            <text className="nrf-chart-tick" x={px(p.x)} y={PLOT.bottom + 13} textAnchor="middle">
              {p.x}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="nrf-figcaption">{caption}</figcaption>
    </figure>
  );
}

function BarChart({
  bars,
  caption,
  ariaLabel,
}: {
  bars: typeof COGNITION_BARS;
  caption: string;
  ariaLabel: string;
}) {
  const shown = bars.filter((b): b is (typeof bars)[number] & { cost: number } => b.cost !== null);
  const { maxY, py } = scales(shown, 1);
  const slot = (PLOT.right - PLOT.left) / bars.length;
  return (
    <figure className="nrf-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel}>
        <Axes maxY={maxY} py={py} />
        {shown.map((b) => {
          const cx = PLOT.left + slot * (bars.indexOf(b) + 0.5);
          return (
            <g key={b.label}>
              <rect
                className="nrf-chart-bar"
                x={cx - 28}
                y={py(b.cost)}
                width={56}
                height={PLOT.bottom - py(b.cost)}
              />
              {b.lo !== undefined && b.hi !== undefined && (
                <RangeBar x={cx} lo={b.lo} hi={b.hi} py={py} />
              )}
              <text
                className="nrf-chart-value"
                x={cx}
                y={py(b.hi ?? b.cost) - 7}
                textAnchor="middle"
              >
                {usd(b.cost)}
              </text>
              <text className="nrf-chart-tick" x={cx} y={PLOT.bottom + 13} textAnchor="middle">
                {b.label}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="nrf-figcaption">{caption}</figcaption>
    </figure>
  );
}

/**
 * The section itself. The cognition-tools panel renders only once its
 * off-cell has a measured cost — a chart with one bar would say nothing.
 */
export function CostSection() {
  const cognitionReady = COGNITION_BARS.every((b) => b.cost !== null);
  return (
    <section className="nrf-section">
      <div className="nrf-container">
        <div className="nrf-narrow">
          <SectionHeading id="cost" level={2} className="nrf-title nrf-title-3 nrf-centered">
            What a day costs
          </SectionHeading>
          <div className="nrf-content nrf-justified">
            <p>
              Every language-model call in a run is metered in-process — tokens, cache traffic, and
              dollars, priced per model — so each simulated day ends with an exact bill. The
              showcase configuration (five agents, twelve hours, Sonnet 5 for the deliberative steps
              and Haiku 4.5 for the conversational ones) costs about{" "}
              <strong>{usd(BASELINE.cost)}</strong> per day, measured across three replicate runs (
              {usd(BASELINE.lo)}–{usd(BASELINE.hi)}). To see how that bill scales, we swept each
              axis separately, holding the others at the showcase values.
            </p>
            <div className="nrf-panes">
              <LineChart
                points={AGENT_POINTS}
                xLabel="agents"
                caption="Cost vs cast size, over a 12-hour day. The 5-agent point is the mean of three replicates; the whiskers span them."
                ariaLabel="Line chart of dollars per run against number of agents: about fifty cents for one agent, three dollars for three, and five dollars ninety for five agents, where a whisker spans the three replicate runs."
              />
              <LineChart
                points={DURATION_POINTS}
                xLabel="simulated hours"
                caption="Cost vs simulated duration, with five agents — linear at roughly $0.49 per simulated hour."
                ariaLabel="Line chart of dollars per run against simulated hours: about one dollar forty for three hours, three dollars for six, and five dollars ninety for twelve, close to a straight line through the origin."
              />
            </div>
            <p>
              Duration scales almost exactly linearly: a settled cast spends tokens at a steady
              rate, so half the day is half the bill. Cast size does not. A solo agent's day costs{" "}
              <strong>{usd(0.518008)}</strong> — far below a per-agent share of the five-agent bill
              — because with nobody to meet, the conversation, scoring, and reaction calls that
              tiering routes to the cheaper model never happen at all (66 calls in the solo day
              against roughly 900 in a five-agent one). The social machinery, not the individual
              deliberation, is where a multi-agent day's budget goes; past three agents the cost per
              agent levels off at roughly a dollar and a quarter per simulated day.
            </p>
            {cognitionReady && (
              <div className="nrf-panes">
                <BarChart
                  bars={COGNITION_BARS}
                  caption="Cognition tools on vs off, at five agents over twelve hours. The on bar is the baseline mean; the whiskers span its three replicates."
                  ariaLabel="Bar chart comparing dollars per run with cognition tools on versus off, at five agents over a twelve-hour day: about five dollars ninety with the tools on, seven dollars with them off."
                />
                <p>
                  And perhaps counterintuitively, disabling the cognition tools — the retrieval
                  calls an agent may make before acting — made the day <em>more</em> expensive (
                  {usd(7.070765)} against the {usd(BASELINE.cost)} baseline, above all three
                  replicates): the tools' own calls are cheap, and agents deciding without recalled
                  context spent more calls overall. That is a single run, so read it as a direction
                  rather than a measurement.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
