import { texts } from "../lib/texts";
import type { CheckResult } from "../lib/types";

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
    <details class="rounded-xl border-2 border-line p-4">
      <summary class="cursor-pointer text-lg font-semibold">{texts.technical.title}</summary>
      <dl class="mt-3 grid gap-x-6 gap-y-1 text-base sm:grid-cols-[auto_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} class="contents">
            <dt class="font-semibold">{label}</dt>
            <dd class="break-all">{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
