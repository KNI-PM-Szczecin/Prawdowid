import { texts } from "../lib/texts";
import type { Badge } from "../lib/types";

export function BadgeList({ badges }: { badges: Badge[] }) {
  if (badges.length === 0) {
    return null;
  }
  return (
    <ul aria-label={texts.badgesLabel} class="flex flex-wrap gap-2">
      {badges.map((badge) => (
        <li key={badge} class="rounded-full border-2 border-line bg-page px-4 py-1.5 text-lg">
          {texts.badges[badge]}
        </li>
      ))}
    </ul>
  );
}
