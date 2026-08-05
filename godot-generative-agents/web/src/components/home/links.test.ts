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
    // Hard-coding the URL is how a link loses its branch. Import `repoTree` /
    // `repoFile` (or `REPO_URL` for the citation) instead.
    expect(src).not.toContain(REPO_URL);
  });
});
