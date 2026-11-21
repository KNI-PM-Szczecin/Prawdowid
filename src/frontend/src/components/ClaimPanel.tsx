import { useEffect, useRef } from "preact/hooks";
import { hasConflict } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { Claim } from "../lib/types";
import "./ClaimPanel.scss";
import { CrossIcon, WarningIcon } from "./Icons";
import { SourceCard } from "./SourceCard";
import { VerdictChip } from "./VerdictChip";

interface ClaimPanelProps {
  claim: Claim;
  onClose: () => void;
}

export function ClaimPanel({ claim, onClose }: ClaimPanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  const conflict = hasConflict(claim);

  // Focus moves to the panel itself (a labelled landmark), not the title, so a mouse click does not
  // draw a focus ring around the claim text. Keyboard users reach the close button with one Tab.
  // The panel is taller than the screen, so the scroll is set explicitly to its top: the browser's
  // focus scroll would align its bottom instead.
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    panel.focus({ preventScroll: true });
    panel.scrollIntoView({ block: "start" });
  }, [claim.id]);

  return (
    <aside id="claim-panel" ref={panelRef} tabIndex={-1} aria-labelledby="claim-panel-title" class="claim-panel">
      <div class="claim-panel__header">
        <h2 id="claim-panel-title" class="claim-panel__title">
          {claim.text}
        </h2>
        <button type="button" onClick={onClose} aria-label={texts.panel.close} class="icon-button">
          <CrossIcon />
        </button>
      </div>

      <VerdictChip claim={claim} />

      <section>
        <h3 class="claim-panel__heading">{texts.panel.justification}</h3>
        <p class="claim-panel__text claim-panel__text--relaxed">{claim.justification}</p>
      </section>

      <section>
        <h3 class="claim-panel__heading">
          {texts.panel.strength}: {texts.strength[claim.evidenceStrength]}
        </h3>
        {claim.strengthReasons.length > 0 && (
          <ul class="claim-panel__bullets">
            {claim.strengthReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
      </section>

      {claim.missing && (
        <section>
          <h3 class="claim-panel__heading">{texts.panel.missing}</h3>
          <p class="claim-panel__text">{claim.missing}</p>
        </section>
      )}

      {claim.warnings.length > 0 && (
        <section>
          <h3 class="claim-panel__heading">{texts.panel.warnings}</h3>
          <ul class="claim-panel__warnings">
            {claim.warnings.map((warning) => (
              <li key={warning.type + warning.message}>
                <strong>{texts.warningType[warning.type]}:</strong> {warning.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section
        class={conflict ? "claim-panel__sources claim-panel__sources--conflict" : "claim-panel__sources"}
        aria-labelledby="sources-title"
      >
        <h3 id="sources-title" class="claim-panel__heading claim-panel__heading--with-icon">
          {conflict && <WarningIcon class="claim-panel__conflict-icon" />}
          {conflict ? texts.panel.conflictTitle : texts.panel.sources}
        </h3>
        {conflict && (
          <p class="claim-panel__text">
            {claim.conflict?.summary ?? ""} {texts.panel.conflictHint}
          </p>
        )}
        {claim.sources.length === 0 ? (
          <p class="claim-panel__text">{texts.panel.noSources}</p>
        ) : (
          <ul class="claim-panel__source-list">
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
