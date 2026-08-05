import { repoFile } from "./links";

/**
 * Where each symbol the page cites is actually defined, so a code reference can
 * land the reader on the function rather than at the top of a 2,000-line file.
 *
 * `path` is repo-relative — the page prints the shorter reading form
 * (`backend/cognition.py`), the link needs the real one
 * (`godot-generative-agents/backend/cognition.py`).
 *
 * `line` is a pin, and pins rot: a line number is right until someone inserts a
 * function above it, and a wrong `#L` anchor still *renders* perfectly. So
 * `codeRefs.test.ts` reads every one of these files off disk and fails when the
 * pinned line no longer holds the definition `def` names. Move a function, and
 * the test tells you which number to bump.
 */
const DEFS = {
  step: {
    path: "godot-generative-agents/backend/run_simulation.py",
    line: 271,
    def: "def step",
  },
  canPerceive: {
    path: "godot-generative-agents/backend/tiled_game.py",
    line: 72,
    def: "def can_perceive",
  },
  planner: {
    path: "godot-generative-agents/backend/planner.py",
    line: 281,
    def: "class LLMPlanner",
  },
  validateStops: {
    path: "text_adventure_games/planning.py",
    line: 282,
    def: "def validate_stops",
  },
  revisePlan: {
    path: "godot-generative-agents/backend/cognition.py",
    line: 1692,
    def: "def maybe_revise_plan",
  },
  retrieve: {
    path: "text_adventure_games/memory.py",
    line: 597,
    def: "def retrieve",
  },
  retrievalConfig: {
    path: "godot-generative-agents/backend/sim_config.py",
    line: 72,
    def: "class RetrievalConfig",
  },
  cognitionToolset: {
    path: "text_adventure_games/npc.py",
    line: 471,
    def: "def cognition_toolset",
  },
  scoreMemories: {
    path: "godot-generative-agents/backend/cognition.py",
    line: 1887,
    def: "def score_new_memories",
  },
  // The reference names should_reflect() *and* reflect(); the link takes the
  // reader to the first, and the second is thirteen lines below it.
  shouldReflect: {
    path: "text_adventure_games/reflection.py",
    line: 174,
    def: "def should_reflect",
  },
  exchange: {
    path: "text_adventure_games/conversation.py",
    line: 159,
    def: "def exchange",
  },
  conversationOutcome: {
    path: "godot-generative-agents/backend/cognition.py",
    line: 1761,
    def: "def apply_conversation_outcome",
  },
  parseCommand: {
    path: "text_adventure_games/parsing.py",
    line: 618,
    def: "def parse_command",
  },
} satisfies Record<string, { path: string; line: number; def: string }>;

export type CodeRefKey = keyof typeof DEFS;

/** The table itself, for the pin test. */
export const codeDefs: Record<CodeRefKey, { path: string; line: number; def: string }> = DEFS;

/** A link straight to a symbol's definition on `prod`. */
export function codeUrl(key: CodeRefKey): string {
  const { path, line } = DEFS[key];
  return `${repoFile(path)}#L${line}`;
}
