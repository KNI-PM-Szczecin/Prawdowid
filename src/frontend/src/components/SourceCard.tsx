import { formatDate } from "../lib/presentation";
import { texts } from "../lib/texts";
import type { Source } from "../lib/types";
import { ExternalIcon } from "./Icons";

export function SourceCard({ source }: { source: Source }) {
  const publishedAt = formatDate(source.publishedAt) ?? texts.panel.noDate;
  const fetchedAt = formatDate(source.fetchedAt);
  return (
    <article class="rounded-xl border-2 border-line bg-page p-4">
      <div class="flex flex-wrap gap-2 text-base font-semibold">
        <span class="rounded-md border border-ink px-2 py-0.5">{texts.sourceRole[source.role]}</span>
        <span class="rounded-md border border-line px-2 py-0.5">{texts.sourceType[source.sourceType]}</span>
      </div>
      <h4 class="mt-2 text-lg font-semibold">{source.title}</h4>
      <p class="text-base">
        {source.publisher}, {texts.panel.published.toLowerCase()} {publishedAt}
        {fetchedAt && `, ${texts.panel.fetched} ${fetchedAt}`}
        {source.license && `. ${texts.panel.license}: ${source.license}`}
      </p>
      <blockquote class="mt-3 border-l-4 border-ink pl-3 text-lg italic">
        <span class="sr-only">{texts.panel.quote}: </span>„{source.quote}”
      </blockquote>
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        class="mt-3 inline-flex items-center gap-1 text-lg font-semibold text-link underline underline-offset-4"
      >
        {texts.panel.openSource}
        <ExternalIcon class="h-4 w-4" />
        <span class="sr-only"> {texts.panel.opensInNewTab}</span>
      </a>
      <p class="mt-1 break-all text-sm text-ink-soft">{source.url}</p>
    </article>
  );
}
