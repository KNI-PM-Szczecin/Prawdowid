import { texts } from "../lib/texts";
import type { CheckResult } from "../lib/types";
import "./TechnicalDetails.scss";

export function TechnicalDetails({ result }: { result: CheckResult }) {
  const { meta } = result;
  const rows: [string, string][] = [
    [texts.technical.requestId, result.requestId],
    [texts.technical.latency, texts.technical.seconds(meta.latencyMs)],
    [texts.technical.model, meta.model ?? texts.technical.none],
    [texts.technical.corpus, meta.corpusVersion ?? texts.technical.none],
    [texts.technical.injection, String(meta.injectionAttempts)],
  ];
  return (
    <details class="technical-details">
      <summary class="technical-details__summary">{texts.technical.title}</summary>
      <dl class="technical-details__list">
        {rows.map(([label, value]) => (
          <div key={label} class="technical-details__row">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
