import { useEffect, useRef } from "preact/hooks";
import { hasConflict } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { Claim } from "../lib/types";
import { CrossIcon, WarningIcon } from "./Icons";
import { SourceCard } from "./SourceCard";
import { VerdictChip } from "./VerdictChip";

interface ClaimPanelProps {
  claim: Claim;
  onClose: () => void;
}

export function ClaimPanel({ claim, onClose }: ClaimPanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const conflict = hasConflict(claim);

  useEffect(() => {
    headingRef.current?.focus();
  }, [claim.id]);

  return (
    <aside id="claim-panel" aria-labelledby="claim-panel-title" class="space-y-6">
      <div class="flex items-start justify-between gap-4">
        <h2 id="claim-panel-title" ref={headingRef} tabIndex={-1} class="text-3xl font-medium leading-tight sm:text-4xl">
          {claim.text}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label={texts.panel.close}
          class="shrink-0 rounded-md border-2 border-ink p-2 hover:bg-neutral-soft"
        >
          <CrossIcon class="h-6 w-6" />
        </button>
      </div>

      <VerdictChip claim={claim} />

      <section>
        <h3 class="text-xl font-semibold">{texts.panel.justification}</h3>
        <p class="mt-1 text-lg leading-relaxed">{claim.justification}</p>
      </section>

      <section>
        <h3 class="text-xl font-semibold">
          {texts.panel.strength}: {texts.strength[claim.evidenceStrength]}
        </h3>
        {claim.strengthReasons.length > 0 && (
          <ul class="mt-1 list-disc pl-6 text-lg">
            {claim.strengthReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
      </section>

      {claim.missing && (
        <section>
          <h3 class="text-xl font-semibold">{texts.panel.missing}</h3>
          <p class="mt-1 text-lg">{claim.missing}</p>
        </section>
      )}

      {claim.warnings.length > 0 && (
        <section>
          <h3 class="text-xl font-semibold">{texts.panel.warnings}</h3>
          <ul class="mt-1 space-y-1 text-lg">
            {claim.warnings.map((warning) => (
              <li key={warning.type + warning.message}>
                <span class="font-semibold">{texts.warningType[warning.type]}:</span> {warning.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section
        class={conflict ? "rounded-2xl border-2 border-warning-line bg-warning-soft p-4 sm:p-6" : undefined}
        aria-labelledby="sources-title"
      >
        <h3 id="sources-title" class="flex items-center gap-2 text-xl font-semibold">
          {conflict && <WarningIcon class="h-6 w-6 text-warning-strong" />}
          {conflict ? texts.panel.conflictTitle : texts.panel.sources}
        </h3>
        {conflict && (
          <p class="mt-1 text-lg">
            {claim.conflict?.summary ?? ""} {texts.panel.conflictHint}
          </p>
        )}
        {claim.sources.length === 0 ? (
          <p class="mt-2 text-lg">{texts.panel.noSources}</p>
        ) : (
          <ul class="mt-3 space-y-3">
            {claim.sources.map((source) => (
              <li key={source.id}>
                <SourceCard source={source} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
