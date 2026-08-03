/**
 * The contents nav, in page order — `id` matches the element it points at (a
 * section for the demo, otherwise the heading itself) and `sub` marks a
 * subsection of the entry above it. `toc.test.ts` pins every id to a real target
 * on the page. Keep the order in sync with the DOM: the scroll-spy relies on it.
 *
 * `number` is derived here so the sidebar and section headings stay in lock-step.
 */
export type TocEntry = {
  id: string;
  label: string;
  sub?: true;
  number?: string;
};

const UNNUMBERED = new Set(["demo", "abstract"]);
const APPENDIX_ID = "appendix";

const RAW_TOC: { id: string; label: string; sub?: true }[] = [
  { id: "demo", label: "Demo" },
  { id: "abstract", label: "Abstract" },
  { id: "case-study", label: "One day, up close" },
  { id: "case-cast", label: "The cast", sub: true },
  { id: "case-dialogs", label: "Three conversations", sub: true },
  { id: "case-goals", label: "Changing plans", sub: true },
  { id: "case-memory", label: "Memory at work", sub: true },
  { id: "case-verdict", label: "What holds up", sub: true },
  { id: "architecture", label: "How an agent works" },
  { id: "world", label: "The world and its clock", sub: true },
  { id: "memory", label: "Memory and retrieval", sub: true },
  { id: "importance", label: "Importance and reflection", sub: true },
  { id: "planning", label: "Planning", sub: true },
  { id: "conversations", label: "Conversations", sub: true },
  { id: "action-gate", label: "The action gate", sub: true },
  { id: "decision", label: "Inside a decision", sub: true },
  // TODO(#880): restore with HomeView's "What's on by default" when Run
  // locally ships with the public codebase (#884) — part of the guide for
  // configuring your own runs.
  // { id: "optional", label: "What's on by default", sub: true },
  { id: "engine", label: "The text-adventure engine" },
  { id: "the-gate", label: "The precondition gate", sub: true },
  { id: "verb-to-tool", label: "From verb to tool", sub: true },
  // TODO(#880): restore with ImplementationSection's "Adding your own verb"
  // when Run locally ships with the public codebase (#884).
  // { id: "your-own-verb", label: "Adding your own verb", sub: true },
  { id: "cost", label: "What a day costs" },
  { id: "reflections", label: "Coding agents as research instruments" },
  { id: "run-locally", label: "Run locally" },
  { id: "prereqs", label: "Prerequisites", sub: true },
  { id: "mock-run", label: "Try it free first", sub: true },
  { id: "key-and-cost", label: "Your key, and what a run costs", sub: true },
  { id: "two-terminal-flow", label: "Run it", sub: true },
  { id: "run-troubleshooting", label: "If something goes wrong", sub: true },
  { id: "extending", label: "Make it your own", sub: true },
  { id: "limitations", label: "Limitations" },
  { id: "appendix", label: "Appendix" },
  { id: "acknowledgements", label: "Acknowledgements", sub: true },
  { id: "assets", label: "Asset packs", sub: true },
  { id: "references", label: "References", sub: true },
];

function annotateToc(entries: typeof RAW_TOC): TocEntry[] {
  let section = 0;
  let subsection = 0;
  let appendixSub = 0;
  let inAppendix = false;

  return entries.map((entry) => {
    if (UNNUMBERED.has(entry.id)) {
      return { ...entry };
    }

    if (entry.id === APPENDIX_ID) {
      inAppendix = true;
      return { ...entry };
    }

    if (inAppendix) {
      if (!entry.sub) {
        throw new Error(`appendix entries must be subsections of ${APPENDIX_ID}: ${entry.id}`);
      }
      appendixSub += 1;
      return { ...entry, number: `A.${appendixSub}` };
    }

    if (entry.sub) {
      subsection += 1;
      return { ...entry, number: `${section}.${subsection}` };
    }
    section += 1;
    subsection = 0;
    return { ...entry, number: String(section) };
  });
}

export const TOC = annotateToc(RAW_TOC);

export function sectionNumber(id: string): string | undefined {
  return TOC.find((e) => e.id === id)?.number;
}
