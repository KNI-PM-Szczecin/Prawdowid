import { texts } from "../lib/texts";
import type { Badge } from "../lib/types";
import "./BadgeList.scss";

export function BadgeList({ badges }: { badges: Badge[] }) {
  // A badge the backend adds before the front knows it is skipped instead of shown as an empty chip.
  const knownBadges = badges.filter((badge) => badge in texts.badges);
  if (knownBadges.length === 0) {
    return null;
  }
  return (
    <ul aria-label={texts.badgesLabel} class="badge-list">
      {knownBadges.map((badge) => (
        <li key={badge} class="badge-list__item">
          {texts.badges[badge]}
        </li>
      ))}
    </ul>
  );
}
