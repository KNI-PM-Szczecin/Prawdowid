import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { formatDate, toneClass, verdictTone } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { CheckResult } from "../lib/types";
import { BadgeList } from "./BadgeList";
import { CampaignAlertBox } from "./CampaignAlertBox";
import { CaseNoticeBox } from "./CaseNoticeBox";
import { ClaimList } from "./ClaimList";
import { ClaimPanel } from "./ClaimPanel";
import { HighlightedText } from "./HighlightedText";
import { MaterialMatchBox } from "./MaterialMatchBox";
import "./ResultView.scss";
import { SummaryBox } from "./SummaryBox";
import { TechnicalDetails } from "./TechnicalDetails";

function isInViewport(element: HTMLElement): boolean {
  const rect = element.getBoundingClientRect();
  return rect.bottom > 0 && rect.top < window.innerHeight;
}

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

  // Opening or closing the drawer reflows the main column, so the clicked claim would jump up or down.
  // Its position on screen is recorded before the change and the page is scrolled by the difference after.
  const scrollAnchorRef = useRef<{ element: HTMLElement; top: number } | null>(null);

  const anchorTo = (element: HTMLElement | null) => {
    scrollAnchorRef.current = element ? { element, top: element.getBoundingClientRect().top } : null;
  };

  useLayoutEffect(() => {
    const anchor = scrollAnchorRef.current;
    if (!anchor) return;
    scrollAnchorRef.current = null;
    const shift = anchor.element.getBoundingClientRect().top - anchor.top;
    if (shift !== 0) window.scrollBy({ top: shift });
  }, [selectedClaimId]);

  // The element that opened the drawer: focus returns to it on close.
  const triggerRef = useRef<HTMLElement | null>(null);

  const selectClaim = (claimId: string, trigger: HTMLElement) => {
    triggerRef.current = trigger;
    anchorTo(trigger);
    setSelectedClaimId(claimId);
  };

  const closePanel = () => {
    const listTrigger = window.document.querySelector<HTMLElement>(`[data-claim-trigger="${selectedClaimId}"]`);
    const trigger = triggerRef.current?.isConnected ? triggerRef.current : listTrigger;
    triggerRef.current = null;
    // The page must not move on close: only a trigger still on screen is held in place through the reflow.
    anchorTo(trigger && isInViewport(trigger) ? trigger : null);
    setSelectedClaimId(null);
    window.requestAnimationFrame(() => {
      (trigger ?? headingRef.current)?.focus({ preventScroll: true });
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
        {document?.url && formatDate(document.publishedAt ?? null) && (
          <p class="result-view__url">
            <strong>{texts.checkedPublishedAt}: </strong>
            {formatDate(document.publishedAt ?? null)}
          </p>
        )}

        {result.summary && <SummaryBox summary={result.summary} />}
        {result.campaignAlert && <CampaignAlertBox alert={result.campaignAlert} />}
        {result.materialMatch && <MaterialMatchBox match={result.materialMatch} />}
        <BadgeList badges={result.badges ?? []} />

        <HighlightedText
          text={document?.text ?? submittedInput}
          claims={result.claims}
          selectedClaimId={selectedClaimId}
          onSelect={selectClaim}
        />

        <ClaimList claims={result.claims} selectedClaimId={selectedClaimId} onSelect={selectClaim} />

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

        <CaseNoticeBox notices={result.cases ?? []} />

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
