import type { ReactNode } from "react";
import { useId } from "react";

/**
 * A pointer into the code, tucked behind a superscript marker so the prose
 * reads as narrative and the file and symbol stay one gesture away.
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
export function CodeRef({ children }: { children: ReactNode }) {
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
      <span role="tooltip" id={id} className="nrf-ref-pop">
        {children}
      </span>
    </span>
  );
}
