import { describe, expect, it } from "vitest";
import { highlight } from "./CodeBlock";

// CodeBlock injects Prism's output with dangerouslySetInnerHTML, exactly as
// TeX.tsx does for KaTeX. These are the checks that the markup is real
// highlighting and that raw source can never inject markup of its own.
describe("landing-page code highlighting", () => {
  it("tokenizes python keywords", () => {
    const html = highlight("def __call__(self):\n    return None", "python");
    expect(html).toContain("token keyword");
    expect(html).toContain("__call__");
  });

  it("tokenizes json properties", () => {
    const html = highlight('{"enum": ["star atlas"]}', "json");
    expect(html).toContain("token property");
    expect(html).toContain("star atlas");
  });

  it("escapes angle brackets so source can't inject markup", () => {
    const html = highlight("x = '<script>'", "python");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});
