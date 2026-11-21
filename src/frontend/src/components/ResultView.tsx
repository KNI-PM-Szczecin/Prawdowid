import { useEffect, useRef, useState } from "preact/hooks";
import { toneClass, verdictTone } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { CheckResult } from "../lib/types";
import { BadgeList } from "./BadgeList";
import { CampaignAlertBox } from "./CampaignAlertBox";
import { ClaimList } from "./ClaimList";
import { ClaimPanel } from "./ClaimPanel";
import { HighlightedText } from "./HighlightedText";
import "./ResultView.scss";
import { SummaryBox } from "./SummaryBox";
import { TechnicalDetails } from "./TechnicalDetails";

interface ResultViewProps {
  result: CheckResult;
  submittedInput: string;
  onNewCheck: () => void;
}

export function ResultView({ result, submittedInput, onNewCheck }: ResultViewProps) {
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelScrollRef = useRef<HTMLDivElement>(null);
  const document = result.document;
  const selectedClaim = result.claims.find((claim) => claim.id === selectedClaimId) ?? null;
  const panelOpen = selectedClaim !== null;

  useEffect(() => headingRef.current?.focus(), [result.requestId]);

  useEffect(() => {
    panelScrollRef.current?.scrollTo({ top: 0 });
  }, [selectedClaimId]);

  const closePanel = () => {
    const claimId = selectedClaimId;
    setSelectedClaimId(null);
    window.requestAnimationFrame(() => {
      const trigger = window.document.querySelector<HTMLElement>(`[data-claim-trigger="${claimId}"]`);
      (trigger ?? headingRef.current)?.focus();
    });
  };

  return (
    <div class={`result-view ${panelOpen ? "result-view--with-panel" : ""}`}>
      <div class="result-view__main">
        <h1 id="main-heading" ref={headingRef} tabIndex={-1} class="result-view__title">
          {document?.title ?? texts.resultTitle}
        </h1>
        {document?.url && (
          <p class="result-view__url">
            <strong>{texts.checkedUrl}: </strong>
            {document.url}
          </p>
        )}

        {result.summary && <SummaryBox summary={result.summary} />}
        {result.campaignAlert && <CampaignAlertBox alert={result.campaignAlert} />}
        <BadgeList badges={result.badges ?? []} />

        <HighlightedText
          text={document?.text ?? submittedInput}
          claims={result.claims}
          selectedClaimId={selectedClaimId}
          onSelect={setSelectedClaimId}
        />

        <ClaimList claims={result.claims} selectedClaimId={selectedClaimId} onSelect={setSelectedClaimId} />

        <section aria-labelledby="limitations-title">
          <h2 id="limitations-title" class="section-title">
            {texts.limitations.title}
          </h2>
          <ul class="result-view__limitations">
            {result.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
            <li>{texts.limitations.general}</li>
          </ul>
        </section>

        <TechnicalDetails result={result} />

        <button type="button" onClick={onNewCheck} class="button button--primary button--large result-view__new">
          {texts.newCheck}
        </button>
      </div>

      {selectedClaim && (
        <div class={`result-view__side ${toneClass(verdictTone(selectedClaim))}`}>
          <div ref={panelScrollRef} class="result-view__side-inner">
            <ClaimPanel claim={selectedClaim} onClose={closePanel} />
          </div>
        </div>
      )}
    </div>
  );
}
