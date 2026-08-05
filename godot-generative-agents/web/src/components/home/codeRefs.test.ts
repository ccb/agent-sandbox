// A `#L` anchor is a pin into someone else's file, and the page has no way to
// know the pin has slipped: insert a function above `score_new_memories` and the
// link still renders, still resolves, and now lands the reader on a blank line in
// the middle of a different function. Nothing about the web build notices.
//
// So read the real Python off disk and check every pinned line still holds the
// definition it claims. `import.meta.glob` with Vite's `?raw` is how the sibling
// links.test.ts reads sources — `node:fs` would mean pulling in @types/node for
// one call, and `tsc -b` type-checks this file.
import { describe, expect, it } from "vitest";
import { codeDefs } from "./codeRefs";

// Two trees, two globs: the engine at the repository root, the simulation backend
// under godot-generative-agents/. Keys come back relative to this file, so they're
// re-keyed to the repo-relative paths codeRefs.ts uses.
const byBasename = (mod: Record<string, string>, prefix: string) =>
  Object.fromEntries(
    Object.entries(mod).map(([key, src]) => [`${prefix}${key.split("/").pop()}`, src]),
  );

const SOURCES: Record<string, string> = {
  ...byBasename(
    import.meta.glob("../../../../../text_adventure_games/*.py", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>,
    "text_adventure_games/",
  ),
  ...byBasename(
    import.meta.glob("../../../../backend/*.py", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>,
    "godot-generative-agents/backend/",
  ),
};

describe("code reference targets", () => {
  it("read the Python trees the references point into", () => {
    // A glob that matched nothing would make every assertion below vacuous: a
    // missing file reads as `undefined`, and the loop would have nothing to check.
    expect(SOURCES["text_adventure_games/memory.py"]).toContain("class AgentMemory");
    expect(SOURCES["godot-generative-agents/backend/cognition.py"]).toContain(
      "def maybe_revise_plan",
    );
  });

  it.each(Object.entries(codeDefs))("%s is still where the link says", (_key, ref) => {
    const src = SOURCES[ref.path];
    expect(src, `${ref.path} is not in the globbed sources`).toBeDefined();
    // 1-indexed, the way GitHub's #L anchor counts.
    expect(src.split("\n")[ref.line - 1]).toContain(ref.def);
  });
});
