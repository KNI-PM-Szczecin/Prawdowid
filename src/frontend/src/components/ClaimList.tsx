import { texts } from "../lib/texts";
import type { Claim } from "../lib/types";
import "./ClaimList.scss";
import { VerdictChip } from "./VerdictChip";

interface ClaimListProps {
  claims: Claim[];
  selectedClaimId: string | null;
  onSelect: (claimId: string, trigger: HTMLElement) => void;
}

// Keyboard and screen-reader path to every claim, also when span is null or highlights are hard to see.
export function ClaimList({ claims, selectedClaimId, onSelect }: ClaimListProps) {
  return (
    <section aria-labelledby="claims-title" class="claim-list">
      <h2 id="claims-title" class="section-title">
        {texts.claims.listTitle(claims.length)}
      </h2>
      {claims.length === 0 ? (
        <p class="claim-list__hint">{texts.claims.noClaims}</p>
      ) : (
        <>
          <p class="claim-list__hint">{texts.claims.listHint}</p>
          <ul class="claim-list__items">
            {claims.map((claim) => (
              <li key={claim.id}>
                <button
                  type="button"
                  onClick={(event) => onSelect(claim.id, event.currentTarget)}
                  data-claim-trigger={claim.id}
                  aria-expanded={claim.id === selectedClaimId}
                  aria-controls="claim-panel"
                  class={`claim-list__item ${claim.id === selectedClaimId ? "claim-list__item--selected" : ""}`}
                >
                  <VerdictChip claim={claim} />
                  <span class="claim-list__text">{claim.text}</span>
                  <span class="claim-list__more">{texts.claims.open}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
