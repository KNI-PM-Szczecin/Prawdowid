import { toneClass, verdictLabel, verdictTone } from "../lib/presentation";
import type { Claim } from "../lib/types";
import "./HighlightedText.scss";

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
  onSelect: (claimId: string, trigger: HTMLElement) => void;
}

export function HighlightedText({ text, claims, selectedClaimId, onSelect }: HighlightedTextProps) {
  return (
    <div class="highlighted-text">
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
            onClick={(event) => onSelect(claim.id, event.currentTarget)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(claim.id, event.currentTarget);
              }
            }}
            class={`highlighted-text__claim ${toneClass(verdictTone(claim))} ${selected ? "highlighted-text__claim--selected" : ""}`}
          >
            {segment.text}
          </span>
        );
      })}
    </div>
  );
}
