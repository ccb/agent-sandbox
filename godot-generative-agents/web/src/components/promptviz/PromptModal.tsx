import { useEffect } from "react";
import { packageLabel } from "./packageLabel";
import type { PromptEntry } from "../../types/promptviz";

interface Props {
  entry: PromptEntry;
  onClose: () => void;
}

/**
 * Pop-up that shows one template's full prompt: declared inputs, the rendered
 * example, and the raw .prompty source. Closes on the backdrop, the × button,
 * or Escape.
 */
export function PromptModal({ entry, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const inputs = entry.inputs;
  const hasInputs = Object.keys(inputs).length > 0;

  return (
    <div className="pcv-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="pcv-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${entry.template} prompt`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="pcv-modal-head">
          <h2 className="pcv-modal-title">
            {entry.template}.prompty
            <span className="pcv-pkg-badge">{packageLabel(entry.package)}</span>
          </h2>
          <button
            type="button"
            className="pcv-modal-close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="pcv-modal-body">
          {entry.description && <p className="pcv-node-desc">{entry.description}</p>}

          {hasInputs && (
            <>
              <div className="pcv-section-label">inputs</div>
              <dl className="pcv-inputs">
                {Object.entries(inputs).map(([name, meta]) => (
                  <div key={name}>
                    <dt>
                      {name}
                      {meta.type ? ` : ${meta.type}` : ""}
                    </dt>
                    {meta.description && <dd>{meta.description}</dd>}
                  </div>
                ))}
              </dl>
            </>
          )}

          {entry.error && <p className="pcv-error">{entry.error}</p>}

          {entry.rendered != null && (
            <>
              <div className="pcv-section-label">rendered (example)</div>
              <pre className="pcv-code">{entry.rendered}</pre>
            </>
          )}

          {entry.raw_source != null && (
            <>
              <div className="pcv-section-label">template source</div>
              <pre className="pcv-code">{entry.raw_source}</pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
