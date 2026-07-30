import katex from "katex";
import "katex/dist/katex.min.css";

/**
 * Render a LaTeX snippet to KaTeX markup.
 *
 * KaTeX is a bundled dependency rather than the usual CDN drop-in: the site
 * runs cross-origin isolated (COOP/COEP), which blocks cross-origin
 * subresources, so Vite emits KaTeX's stylesheet and fonts same-origin
 * instead. `throwOnError: false` keeps one bad formula from blanking the whole
 * page — KaTeX renders it in red, and `formulas.test.ts` fails on it.
 *
 * ponytail: KaTeX rides in the main chunk (~78 kB gzip); lazy-load it or
 * prerender the formulas at build time if landing-page load ever matters.
 */
export function renderTeX(tex: string, displayMode: boolean): string {
  return katex.renderToString(tex, { displayMode, throwOnError: false });
}

/** Inline math by default; `display` gives a centered block. */
export function TeX({ children, display = false }: { children: string; display?: boolean }) {
  const html = renderTeX(children, display);
  return display ? (
    // biome-ignore lint/security/noDangerouslySetInnerHtml: KaTeX markup rendered from in-repo literals
    <div className="nrf-math" dangerouslySetInnerHTML={{ __html: html }} />
  ) : (
    // biome-ignore lint/security/noDangerouslySetInnerHtml: KaTeX markup rendered from in-repo literals
    <span dangerouslySetInnerHTML={{ __html: html }} />
  );
}
