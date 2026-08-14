import { describe, expect, it } from "vitest";
// A link to our own repository that omits the branch lands the reader on `main`,
// which is not what the public reads — and it renders fine, so nothing else
// catches it. Pin the two rules that prevent it: the helpers name `prod`, and no
// component spells the repo URL out by hand instead of importing them.
//
// `import.meta.glob` reads every sibling source as a string (Vite's `?raw`), so
// this covers files that don't exist yet without anyone remembering to add them
// here. `node:fs` would mean pulling in @types/node just for this.
import { REPO_URL, repoFile, repoTree } from "./links";

const SOURCES = import.meta.glob("./*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// links.ts is where the URL is allowed to be a literal; its own test may quote
// it too (the assertions below do).
const ALLOWED = ["./links.ts", "./links.test.ts"];

describe("repository links", () => {
  it("points the browse link at prod, not the default branch", () => {
    expect(repoTree).toBe("https://github.com/ccb/agent-sandbox/tree/prod");
  });

  it("points file links at prod", () => {
    expect(repoFile("godot-generative-agents/README.md")).toBe(
      "https://github.com/ccb/agent-sandbox/blob/prod/godot-generative-agents/README.md",
    );
  });

  it("globbed the sources it means to check", () => {
    // A glob that silently matches nothing would make the rule below vacuous.
    expect(Object.keys(SOURCES)).toContain("./HomeView.tsx");
    expect(Object.keys(SOURCES)).toContain("./RunLocallySection.tsx");
  });

  it.each(
    Object.entries(SOURCES).filter(([path]) => !ALLOWED.includes(path)),
    // biome-ignore lint/suspicious/noExplicitAny: it.each's tuple typing
  )("%s builds repo links from links.ts", (_path: any, src: any) => {
    // Hard-coding the URL is how a link loses its branch. Import `repoTree` or
    // `repoFile` instead — including in the citation, which names `prod` too.
    expect(src).not.toContain(REPO_URL);
  });

  it("cites prod, not the default branch", () => {
    // The citation is the one repo link a reader copies away from the page, so
    // it outlives every other one here. `not.toContain(REPO_URL)` above already
    // rejects a hand-written URL; this pins what the template interpolates, so
    // reverting it to the bare `REPO_URL` fails rather than silently shipping a
    // citation that resolves to `main`.
    const home = SOURCES["./HomeView.tsx"];
    expect(home).toContain("url    = {${repoTree}}");
  });
});
