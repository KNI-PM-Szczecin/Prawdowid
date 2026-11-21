import { texts } from "../lib/texts";
import type { CampaignAlert } from "../lib/types";
import "./CampaignAlertBox.scss";
import { LandmarkIcon } from "./Icons";

// Context only (brief, scenario I): the text comes verbatim from rag/ and never states the submission is false.
export function CampaignAlertBox({ alert }: { alert: CampaignAlert }) {
  return (
    <section aria-labelledby="campaign-title" class="campaign-alert">
      <span class="campaign-alert__icon" aria-hidden="true">
        <LandmarkIcon class="campaign-alert__glyph" />
      </span>
      <div>
        <h2 id="campaign-title" class="campaign-alert__title">
          {texts.campaign.title}
        </h2>
        <p class="campaign-alert__text">{alert.message}</p>
        {alert.matches.length > 0 && (
          <div class="campaign-alert__matches">
            <h3 class="campaign-alert__matches-title">{texts.campaign.matchesLabel}:</h3>
            <ul class="campaign-alert__list">
              {alert.matches.map((match) => (
                <li key={match.incidentId}>
                  <a href={match.url} target="_blank" rel="noopener noreferrer" class="campaign-alert__link">
                    {match.title}
                    <span class="sr-only"> {texts.panel.opensInNewTab}</span>
                  </a>
                  <p class="campaign-alert__match-summary">
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
