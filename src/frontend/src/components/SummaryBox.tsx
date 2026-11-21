import { SUMMARY_TONE, TONE_CLASSES } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { Summary } from "../lib/types";
import { StatusIcon } from "./StatusIcon";

export function SummaryBox({ summary }: { summary: Summary }) {
  const tone = SUMMARY_TONE[summary.level];
  const copy = texts.summary[summary.level];
  return (
    <section
      aria-labelledby="summary-title"
      class={`flex flex-col gap-5 rounded-3xl border-2 p-6 sm:flex-row sm:items-center sm:p-8 ${TONE_CLASSES[tone].box}`}
    >
      <StatusIcon tone={tone} />
      <div>
        <h2 id="summary-title" class="text-2xl font-semibold">
          {copy.title}
        </h2>
        <p class="mt-1 text-lg">{copy.description}</p>
        {summary.reasons.length > 0 && (
          <p class="mt-2 text-lg">
            <span class="font-semibold">{texts.summaryReasonsLabel}: </span>
            {summary.reasons.join(", ")}.
          </p>
        )}
      </div>
    </section>
  );
}
