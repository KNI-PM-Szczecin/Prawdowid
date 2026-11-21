import { texts } from "../lib/texts";
import type { CampaignAlert } from "../lib/types";
import { LandmarkIcon } from "./Icons";

// Context only (brief, scenario I): the text comes verbatim from rag/ and never states the submission is false.
export function CampaignAlertBox({ alert }: { alert: CampaignAlert }) {
  return (
    <section
      aria-labelledby="campaign-title"
      class="flex flex-col gap-5 rounded-3xl border-2 border-alert-line bg-alert p-6 text-alert-ink sm:flex-row sm:items-start sm:p-8"
    >
      <span
        class="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-[10px] border-alert-ring bg-alert-ink text-alert"
        aria-hidden="true"
      >
        <LandmarkIcon class="h-9 w-9" />
      </span>
      <div>
        <h2 id="campaign-title" class="text-2xl font-semibold">
          {texts.campaign.title}
        </h2>
        <p class="mt-1 text-lg">{alert.message}</p>
        {alert.matches.length > 0 && (
          <div class="mt-3">
            <h3 class="text-lg font-semibold">{texts.campaign.matchesLabel}:</h3>
            <ul class="mt-1 space-y-2">
              {alert.matches.map((match) => (
                <li key={match.incidentId}>
                  <a
                    href={match.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-lg font-semibold text-alert-ink underline underline-offset-4"
                  >
                    {match.title}
                    <span class="sr-only"> {texts.panel.opensInNewTab}</span>
                  </a>
                  <p class="text-base">
                    {match.summary} {texts.source}: {match.source}.
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
