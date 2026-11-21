import { useEffect, useRef, useState } from "preact/hooks";
import { texts } from "../lib/texts";
import type { CheckResult } from "../lib/types";
import { BadgeList } from "./BadgeList";
import { CampaignAlertBox } from "./CampaignAlertBox";
import { ClaimList } from "./ClaimList";
import { ClaimPanel } from "./ClaimPanel";
import { HighlightedText } from "./HighlightedText";
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
  const document = result.document;
  const selectedClaim = result.claims.find((claim) => claim.id === selectedClaimId) ?? null;
  const panelOpen = selectedClaim !== null;

  useEffect(() => headingRef.current?.focus(), [result.requestId]);

  const closePanel = () => {
    const claimId = selectedClaimId;
    setSelectedClaimId(null);
    window.requestAnimationFrame(() => {
      const trigger = window.document.querySelector<HTMLElement>(`[data-claim-trigger="${claimId}"]`);
      (trigger ?? headingRef.current)?.focus();
    });
  };

  return (
    <div class={`mx-auto px-4 py-8 sm:px-8 ${panelOpen ? "max-w-7xl" : "max-w-5xl"}`}>
      <div class={panelOpen ? "grid gap-10 lg:grid-cols-2 lg:gap-0" : ""}>
        <div class={`space-y-8 ${panelOpen ? "lg:border-r-2 lg:border-line lg:pr-8" : ""}`}>
          <h1 id="main-heading" ref={headingRef} tabIndex={-1} class="text-3xl font-semibold leading-tight sm:text-5xl sm:leading-tight">
            {document?.title ?? texts.resultTitle}
          </h1>
          {document?.url && (
            <p class="break-all text-lg">
              <span class="font-semibold">{texts.checkedUrl}: </span>
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
            <h2 id="limitations-title" class="text-2xl font-semibold">
              {texts.limitations.title}
            </h2>
            <ul class="mt-2 list-disc space-y-1 pl-6 text-lg">
              {result.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
              <li>{texts.limitations.general}</li>
            </ul>
          </section>

          <TechnicalDetails result={result} />

          <button
            type="button"
            onClick={onNewCheck}
            class="rounded-xl bg-ink px-6 py-4 text-xl font-semibold text-page hover:opacity-90"
          >
            {texts.newCheck}
          </button>
        </div>

        {selectedClaim && (
          <div class="lg:pl-8">
            <div class="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto lg:pr-2">
              <ClaimPanel claim={selectedClaim} onClose={closePanel} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
