import Prism from "prismjs";
import "prismjs/components/prism-python";
import "prismjs/components/prism-json";

/**
 * Highlight a snippet to Prism markup.
 *
 * Prism is a bundled dependency rather than the usual CDN drop-in, for the same
 * reason KaTeX is (see TeX.tsx): the site runs cross-origin isolated
 * (COOP/COEP), which blocks cross-origin subresources. Only the Python and JSON
 * grammars are imported, so Vite leaves the rest of Prism out of the bundle.
 *
 * No Prism stylesheet: token colors come from the --nrf-code-* variables in
 * home.css, which keeps them in the landing page's palette. The page is
 * light-only (see theme.css), so there is no dark variant to match.
 *
 * Prism escapes < in the source it tokenizes, but misses some > characters.
 * We post-process to escape > outside of tags, making the HTML safe for
 * dangerouslySetInnerHTML — CodeBlock.test.ts pins that.
 */
export function highlight(code: string, lang: "python" | "json"): string {
  const highlighted = Prism.highlight(code, Prism.languages[lang], lang);

  // Escape > that are outside HTML tags (in text content)
  let result = "";
  let inTag = false;

  for (let i = 0; i < highlighted.length; i++) {
    const char = highlighted[i];

    if (char === "<") {
      inTag = true;
      result += char;
    } else if (char === ">") {
      if (inTag) {
        inTag = false;
        result += char;
      } else {
        result += "&gt;";
      }
    } else {
      result += char;
    }
  }

  return result;
}

/**
 * One highlighted snippet with an optional caption. `code` arrives from a real
 * file under snippets/ via Vite's `?raw`, so it is the same bytes the pin test
 * in tests/test_landing_snippets.py reads.
 */
export function CodeBlock({
  code,
  lang,
  caption,
}: {
  code: string;
  lang: "python" | "json";
  caption?: string;
}) {
  return (
    <div className="nrf-code">
      <pre className={`nrf-pre language-${lang}`}>
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: Prism markup, from in-repo snippet files, and Prism escapes the source */}
        <code dangerouslySetInnerHTML={{ __html: highlight(code.trimEnd(), lang) }} />
      </pre>
      {caption && <p className="nrf-code-caption">{caption}</p>}
    </div>
  );
}
