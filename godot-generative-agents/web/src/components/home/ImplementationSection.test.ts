import { describe, expect, it } from "vitest";
import { highlight } from "./CodeBlock";
import { SNIPPETS } from "./ImplementationSection";

// The snippets are real files loaded with `?raw`. A wrong path yields an empty
// string rather than a build error, so an empty snippet would ship as a blank
// box on the public page — that is what this catches. tests/test_landing_snippets.py
// is what pins their *content* to the engine.
describe("Implementation section snippets", () => {
  it.each(Object.entries(SNIPPETS))("%s is non-empty", (_name, snippet) => {
    expect(snippet.code.trim().length).toBeGreaterThan(20);
  });

  it.each(Object.entries(SNIPPETS))("%s highlights without losing its source", (_name, snippet) => {
    const html = highlight(snippet.code, snippet.lang);
    expect(html).toContain("token");
  });

  it("loads the gate contract and the derived tool", () => {
    expect(SNIPPETS.gate.code).toContain("check_preconditions");
    expect(SNIPPETS.tool.code).toContain('"enum"');
    expect(SNIPPETS.tool.lang).toBe("json");
  });
});
