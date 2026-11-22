import { formatDate } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { MaterialMatch } from "../lib/types";
import { InfoIcon } from "./Icons";
import "./MaterialMatchBox.scss";

// Brief scenario I: the page was recognised as a known material. The basis is spelled out and the box never
// says anything about the truth of the content; the message comes verbatim from agent/.
export function MaterialMatchBox({ match }: { match: MaterialMatch }) {
  return (
    <section aria-labelledby="material-title" class="material-match">
      <span class="material-match__icon" aria-hidden="true">
        <InfoIcon class="material-match__glyph" />
      </span>
      <div>
        <h2 id="material-title" class="material-match__title">
          {texts.material.title}
        </h2>
        <p class="material-match__text">{match.message}</p>
        <ul class="material-match__list">
          {match.matches.map((item) => (
            <li key={item.url + item.basis.join("+")}>
              <a href={item.url} target="_blank" rel="noopener noreferrer" class="material-match__link">
                {item.title}
                <span class="sr-only"> {texts.panel.opensInNewTab}</span>
              </a>
              <p class="material-match__meta">
                {texts.material.kind[item.kind]}, {item.publisher}
                {formatDate(item.publishedAt) ? `, ${formatDate(item.publishedAt)}` : ""}.{" "}
                {texts.material.basisLabel}: {item.basis.map((basis) => texts.material.basis[basis]).join(", ")}.
              </p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
