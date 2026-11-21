import { useEffect, useRef } from "preact/hooks";
import { texts } from "../lib/texts";
import type { CheckResult } from "../lib/types";
import { InfoIcon } from "./Icons";

interface StatusViewProps {
  title: string;
  message: string;
  note?: string;
  onRetry?: () => void;
  onBack: () => void;
}

// Non-merit states look different from verdicts on purpose (brief): no verdict colours, no summary box.
export function StatusView({ title, message, note, onRetry, onBack }: StatusViewProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);

  return (
    <div class="mx-auto max-w-3xl px-4 py-16 sm:px-8">
      <div role="alert" class="rounded-3xl border-2 border-ink bg-page p-6 sm:p-8">
        <div class="flex items-start gap-4">
          <InfoIcon class="h-10 w-10 shrink-0" />
          <div>
            <h1 id="main-heading" ref={headingRef} tabIndex={-1} class="text-3xl font-semibold">
              {title}
            </h1>
            <p class="mt-3 text-xl">{message}</p>
            {note && <p class="mt-2 text-xl font-semibold">{note}</p>}
          </div>
        </div>
        <div class="mt-6 flex flex-wrap gap-3">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              class="rounded-xl bg-ink px-6 py-3 text-lg font-semibold text-page hover:opacity-90"
            >
              {texts.status.retry}
            </button>
          )}
          <button
            type="button"
            onClick={onBack}
            class="rounded-xl border-2 border-ink px-6 py-3 text-lg font-semibold hover:bg-neutral-soft"
          >
            {texts.status.back}
          </button>
        </div>
      </div>
    </div>
  );
}

export function statusCopy(result: CheckResult): { title: string; note?: string; retryable: boolean } {
  switch (result.status) {
    case "technical_error":
      return { title: texts.status.technicalErrorTitle, note: texts.status.technicalErrorNote, retryable: true };
    case "out_of_scope":
      return { title: texts.status.outOfScopeTitle, retryable: false };
    default:
      return { title: texts.status.needsClarificationTitle, retryable: false };
  }
}
