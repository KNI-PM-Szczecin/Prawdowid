import { texts } from "../lib/texts";
import type { Claim } from "../lib/types";
import { VerdictChip } from "./VerdictChip";

interface ClaimListProps {
  claims: Claim[];
  selectedClaimId: string | null;
  onSelect: (claimId: string) => void;
}

// Keyboard and screen-reader path to every claim, also when span is null or highlights are hard to see.
export function ClaimList({ claims, selectedClaimId, onSelect }: ClaimListProps) {
  return (
    <section aria-labelledby="claims-title">
      <h2 id="claims-title" class="text-2xl font-semibold">
        {texts.claims.listTitle(claims.length)}
      </h2>
      {claims.length === 0 ? (
        <p class="mt-2 text-lg">{texts.claims.noClaims}</p>
      ) : (
        <>
          <p class="mt-1 text-lg">{texts.claims.listHint}</p>
          <ul class="mt-4 space-y-3">
            {claims.map((claim) => (
              <li key={claim.id}>
                <button
                  type="button"
                  onClick={() => onSelect(claim.id)}
                  data-claim-trigger={claim.id}
                  aria-expanded={claim.id === selectedClaimId}
                  aria-controls="claim-panel"
                  class={`flex w-full flex-col items-start gap-2 rounded-xl border-2 p-4 text-left hover:border-ink ${claim.id === selectedClaimId ? "border-ink" : "border-line"}`}
                >
                  <VerdictChip claim={claim} />
                  <span class="text-lg">{claim.text}</span>
                  <span class="text-base font-semibold underline underline-offset-4">{texts.claims.open}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
