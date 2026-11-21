import { TONE_CLASSES, verdictLabel, verdictTone } from "../lib/presentation";
import type { Claim } from "../lib/types";
import { StatusIcon } from "./StatusIcon";

export function VerdictChip({ claim }: { claim: Claim }) {
  const tone = verdictTone(claim);
  return (
    <span
      class={`inline-flex items-center gap-2 rounded-full border-2 px-3 py-1 text-lg font-medium text-ink ${TONE_CLASSES[tone].chip}`}
    >
      <StatusIcon tone={tone} size="small" />
      {verdictLabel(claim)}
    </span>
  );
}
