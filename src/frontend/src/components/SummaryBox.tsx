import { SUMMARY_TONE, summaryCopy, toneClass } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { Claim, Summary } from "../lib/types";
import { StatusIcon } from "./StatusIcon";
import "./SummaryBox.scss";

export function SummaryBox({ summary, claims }: { summary: Summary; claims: Claim[] }) {
  const tone = SUMMARY_TONE[summary.level];
  const copy = summaryCopy(summary, claims);
  return (
    <section aria-labelledby="summary-title" class={`summary-box ${toneClass(tone)}`}>
      <StatusIcon tone={tone} />
      <div>
        <h2 id="summary-title" class="summary-box__title">
          {copy.title}
        </h2>
        <p class="summary-box__text">{copy.description}</p>
        {summary.reasons.length > 0 && (
          <p class="summary-box__reasons">
            <strong>{texts.summaryReasonsLabel}: </strong>
            {summary.reasons.join(", ")}.
          </p>
        )}
      </div>
    </section>
  );
}
