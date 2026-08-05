import type { ReactNode } from "react";
import { useId } from "react";
import { type CodeRefKey, codeUrl } from "./codeRefs";

/**
 * A pointer into the code, tucked behind a superscript marker so the prose
 * reads as narrative and the file and symbol stay one gesture away.
 *
 * The reference is a link to the named symbol's own definition on `prod`: `at`
 * picks the entry in codeRefs.ts that carries the file and the line. Naming a
 * function and leaving the reader to go find it is half a reference. The popup
 * *is* the anchor rather than containing one, so there is nothing extra to aim
 * at once it has opened, and hovering it keeps `.nrf-ref:hover` true.
 *
 * The marker is a real `<button>`, which is what makes this work beyond a
 * mouse: hover, keyboard focus and tap all land on `:hover`/`:focus-within`, so
 * a phone reader is not shut out of content a desktop reader gets. The
 * reference itself is always in the DOM — never generated in CSS — so screen
 * readers announce it, Ctrl-F finds it, and it survives with the text on copy.
 *
 * Below 640px the popup would have nowhere to go without pushing the page
 * sideways, so the stylesheet hides the marker and prints the reference inline
 * as a parenthetical instead. Same markup, two presentations.
 */
export function CodeRef({ at, children }: { at: CodeRefKey; children: ReactNode }) {
  const id = useId();
  return (
    <span className="nrf-ref">
      <button
        type="button"
        className="nrf-ref-mark"
        aria-describedby={id}
        aria-label="Where this lives in the code"
      >
        {"</>"}
      </button>
      {/* No role="tooltip": this is a link, and that role would hide the fact
          from a screen reader. aria-describedby works on any element. */}
      <a id={id} className="nrf-ref-pop" href={codeUrl(at)} target="_blank" rel="noreferrer">
        {children}
      </a>
    </span>
  );
}
