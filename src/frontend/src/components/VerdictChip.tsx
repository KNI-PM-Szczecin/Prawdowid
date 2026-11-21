import { toneClass, verdictLabel, verdictTone } from "../lib/presentation";
import type { Claim } from "../lib/types";
import { StatusIcon } from "./StatusIcon";
import "./VerdictChip.scss";

export function VerdictChip({ claim }: { claim: Claim }) {
  const tone = verdictTone(claim);
  return (
    <span class={`verdict-chip ${toneClass(tone)}`}>
      <StatusIcon tone={tone} size="small" />
      {verdictLabel(claim)}
    </span>
  );
}
