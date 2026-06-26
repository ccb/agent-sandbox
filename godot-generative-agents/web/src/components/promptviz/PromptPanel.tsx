import type { PromptDetail } from "../../types/promptviz";

interface Props {
  detail: PromptDetail | null;
}

/**
 * The right-hand detail panel. Ported from promptviz.js showPrompt(): a node's
 * title + kind badge, description, and — for templated nodes — the declared
 * inputs, the rendered example prompt, and the raw .prompty source. The run
 * overlay's "actual calls" section is omitted in the static port.
 */
export function PromptPanel({ detail }: Props) {
  if (!detail) {
    return <div className="pcv-panel-empty">Click a node to read its prompt.</div>;
  }

  const inputs = detail.frontmatter?.inputs;
  const hasInputs = inputs && Object.keys(inputs).length > 0;

  return (
    <div className="pcv-panel-body">
      <h2 className="pcv-node-title">
        {detail.label}
        <span className={`pcv-kind-badge ${detail.kind}`}>{detail.kind}</span>
      </h2>

      {detail.description && <p className="pcv-node-desc">{detail.description}</p>}
      {detail.note && <p className="pcv-note">{detail.note}</p>}

      {detail.template && (
        <>
          <div className="pcv-section-label">template</div>
          <div className="pcv-template-name">{detail.template}.prompty</div>

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

          {detail.error && <p className="pcv-error">{detail.error}</p>}

          {detail.rendered != null && (
            <>
              <div className="pcv-section-label">rendered (example)</div>
              <pre className="pcv-code">{detail.rendered}</pre>
            </>
          )}

          {detail.raw_source != null && (
            <>
              <div className="pcv-section-label">template source</div>
              <pre className="pcv-code">{detail.raw_source}</pre>
            </>
          )}
        </>
      )}
    </div>
  );
}
