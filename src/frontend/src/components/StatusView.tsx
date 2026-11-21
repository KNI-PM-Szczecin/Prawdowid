import { useEffect, useRef } from "preact/hooks";
import { texts } from "../lib/texts";
import type { CheckResult } from "../lib/types";
import { InfoIcon } from "./Icons";
import "./StatusView.scss";

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
    <div class="status-view">
      <div role="alert" class="status-view__card">
        <div class="status-view__body">
          <InfoIcon class="status-view__icon" />
          <div>
            <h1 id="main-heading" ref={headingRef} tabIndex={-1} class="status-view__title">
              {title}
            </h1>
            <p class="status-view__message">{message}</p>
            {note && <p class="status-view__note">{note}</p>}
          </div>
        </div>
        <div class="status-view__actions">
          {onRetry && (
            <button type="button" onClick={onRetry} class="button button--primary">
              {texts.status.retry}
            </button>
          )}
          <button type="button" onClick={onBack} class="button button--secondary">
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
