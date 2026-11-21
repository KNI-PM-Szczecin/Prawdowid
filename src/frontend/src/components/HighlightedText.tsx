import { TONE_CLASSES, verdictLabel, verdictTone } from "../lib/presentation";
import type { Claim } from "../lib/types";

interface Segment {
  text: string;
  claim: Claim | null;
}

// claims[].span is in Unicode code points (CONTRACT.md §1a), hence Array.from instead of string indices.
function buildSegments(text: string, claims: Claim[]): Segment[] {
  const characters = Array.from(text);
  const located = claims
    .filter((claim) => claim.span && claim.span.start < claim.span.end && claim.span.end <= characters.length)
    .sort((first, second) => (first.span?.start ?? 0) - (second.span?.start ?? 0));

  const segments: Segment[] = [];
  let cursor = 0;
  for (const claim of located) {
    const { start, end } = claim.span!;
    if (start < cursor) {
      continue;
    }
    if (start > cursor) {
      segments.push({ text: characters.slice(cursor, start).join(""), claim: null });
    }
    segments.push({ text: characters.slice(start, end).join(""), claim });
    cursor = end;
  }
  if (cursor < characters.length) {
    segments.push({ text: characters.slice(cursor).join(""), claim: null });
  }
  return segments;
}

interface HighlightedTextProps {
  text: string;
  claims: Claim[];
  selectedClaimId: string | null;
  onSelect: (claimId: string) => void;
}

export function HighlightedText({ text, claims, selectedClaimId, onSelect }: HighlightedTextProps) {
  return (
    <div class="whitespace-pre-line text-xl leading-loose sm:text-2xl sm:leading-loose">
      {buildSegments(text, claims).map((segment, index) => {
        const claim = segment.claim;
        if (!claim) {
          return <span key={index}>{segment.text}</span>;
        }
        const selected = claim.id === selectedClaimId;
        return (
          <span
            key={index}
            role="button"
            tabIndex={0}
            aria-expanded={selected}
            aria-controls="claim-panel"
            aria-label={`${segment.text} (${verdictLabel(claim)})`}
            onClick={() => onSelect(claim.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(claim.id);
              }
            }}
            class={`cursor-pointer rounded-md border-b-4 px-1 [box-decoration-break:clone] hover:brightness-95 ${TONE_CLASSES[verdictTone(claim)].highlight} ${selected ? "outline-2 outline-offset-2 outline-ink" : ""}`}
          >
            {segment.text}
          </span>
        );
      })}
    </div>
  );
}
