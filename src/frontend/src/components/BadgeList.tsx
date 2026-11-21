import { texts } from "../lib/texts";
import type { Badge } from "../lib/types";
import "./BadgeList.scss";

export function BadgeList({ badges }: { badges: Badge[] }) {
  if (badges.length === 0) {
    return null;
  }
  return (
    <ul aria-label={texts.badgesLabel} class="badge-list">
      {badges.map((badge) => (
        <li key={badge} class="badge-list__item">
          {texts.badges[badge]}
        </li>
      ))}
    </ul>
  );
}
