import { formatDate } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { Source } from "../lib/types";
import { ExternalIcon } from "./Icons";
import "./SourceCard.scss";

export function SourceCard({ source }: { source: Source }) {
  const publishedAt = formatDate(source.publishedAt) ?? texts.panel.noDate;
  const fetchedAt = formatDate(source.fetchedAt);
  return (
    <article class="source-card">
      <div class="source-card__tags">
        <span class="source-card__tag source-card__tag--role">{texts.sourceRole[source.role]}</span>
        <span class="source-card__tag">{texts.sourceType[source.sourceType]}</span>
      </div>
      <h4 class="source-card__title">{source.title}</h4>
      <p class="source-card__meta">
        {source.publisher}, {texts.panel.published.toLowerCase()} {publishedAt}
        {fetchedAt && `, ${texts.panel.fetched} ${fetchedAt}`}
        {source.license && `. ${texts.panel.license}: ${source.license}`}
      </p>
      <blockquote class="source-card__quote">
        <span class="sr-only">{texts.panel.quote}: </span>„{source.quote}”
      </blockquote>
      <a href={source.url} target="_blank" rel="noopener noreferrer" class="source-card__link">
        {texts.panel.openSource}
        <ExternalIcon class="source-card__link-icon" />
        <span class="sr-only"> {texts.panel.opensInNewTab}</span>
      </a>
      <p class="source-card__url">{source.url}</p>
    </article>
  );
}
