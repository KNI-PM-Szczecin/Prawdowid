import { texts } from "../lib/texts";
import type { SourceType, Verdict } from "../lib/types";
import { CheckForm } from "./CheckForm";
import "./Landing.scss";
import { StatusIcon } from "./StatusIcon";
import "./VerdictChip.scss";
import { toneClass, type Tone } from "../lib/presentation";

interface LandingProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onSubmitImage: (image: File) => void;
}

const VERDICT_ORDER: { verdict: Verdict; tone: Tone }[] = [
  { verdict: "confirmed", tone: "positive" },
  { verdict: "false", tone: "negative" },
  { verdict: "misleading", tone: "warning" },
  { verdict: "insufficient_evidence", tone: "neutral" },
  { verdict: "not_verifiable", tone: "neutral" },
];

const SOURCE_ORDER: SourceType[] = ["official", "factcheck", "secondary", "reference", "incident"];

const SAMPLE_TONE: Record<"confirmed" | "conflicting", Tone> = { confirmed: "positive", conflicting: "warning" };

export function Landing({ value, onChange, onSubmit, onSubmitImage }: LandingProps) {
  return (
    <div class="landing">
      <section class="landing__hero" aria-labelledby="main-heading">
        <h1 id="main-heading" tabIndex={-1} class="landing__title">
          {texts.form.title}
        </h1>
        <p class="landing__lead">{texts.form.lead}</p>
        <CheckForm value={value} onChange={onChange} onSubmit={onSubmit} onSubmitImage={onSubmitImage} />
      </section>

      <section class="landing__section landing__section--sample" aria-labelledby="sample-title">
        <h2 id="sample-title" class="landing__section-title">
          {texts.landing.sampleTitle}
          <span class="landing__section-subtitle">{texts.landing.sampleNote}</span>
        </h2>
        <div class="landing__sample">
          <p class="landing__sample-text">
            {texts.landing.sampleSentence.before}
            <mark class={`landing__mark ${toneClass("positive")}`}>{texts.landing.sampleSentence.confirmed}</mark>
            {texts.landing.sampleSentence.middle}
            <mark class={`landing__mark ${toneClass("warning")}`}>{texts.landing.sampleSentence.conflicting}</mark>
            {texts.landing.sampleSentence.after}
          </p>
          <ul class="landing__sample-claims">
            {texts.landing.sampleClaims.map((claim) => (
              <li key={claim.verdict} class="landing__sample-claim">
                <span class={`verdict-chip ${toneClass(SAMPLE_TONE[claim.verdict])}`}>
                  <StatusIcon tone={SAMPLE_TONE[claim.verdict]} size="small" />
                  {claim.label}
                </span>
                <span class="landing__sample-claim-text">{claim.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section class="landing__section" aria-labelledby="process-title">
        <h2 id="process-title" class="landing__section-title">
          {texts.landing.processTitle}
        </h2>
        <ol class="landing__steps">
          {texts.landing.steps.map((step, index) => (
            <li key={step.title} class="landing__step">
              <span class="landing__step-number" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <h3 class="landing__step-title">{step.title}</h3>
                <p class="landing__step-text">{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section class="landing__section" aria-labelledby="verdicts-title">
        <h2 id="verdicts-title" class="landing__section-title">
          {texts.landing.verdictsTitle}
        </h2>
        <p class="landing__section-lead">{texts.landing.verdictsLead}</p>
        <dl class="landing__verdicts">
          {VERDICT_ORDER.map(({ verdict, tone }) => (
            <div key={verdict} class="landing__verdict">
              <dt class="landing__verdict-name">
                <StatusIcon tone={tone} size="small" />
                {texts.verdict[verdict]}
              </dt>
              <dd class="landing__verdict-text">{texts.landing.verdictDescriptions[verdict]}</dd>
            </div>
          ))}
        </dl>
        <p class="landing__section-note">{texts.landing.verdictsNote}</p>
      </section>

      <section class="landing__section" aria-labelledby="sources-title">
        <h2 id="sources-title" class="landing__section-title">
          {texts.landing.sourcesTitle}
        </h2>
        <dl class="landing__sources">
          {SOURCE_ORDER.map((sourceType) => (
            <div key={sourceType} class="landing__source">
              <dt class="landing__source-name">{texts.sourceType[sourceType]}</dt>
              <dd class="landing__source-text">{texts.landing.sourceDescriptions[sourceType]}</dd>
            </div>
          ))}
        </dl>
        <p class="landing__section-note">{texts.landing.sourcesNote}</p>
      </section>

      <section class="landing__section" aria-labelledby="principles-title">
        <h2 id="principles-title" class="landing__section-title">
          {texts.landing.principlesTitle}
        </h2>
        <ul class="landing__principles">
          {texts.landing.principles.map((principle) => (
            <li key={principle.title} class="landing__principle">
              <h3 class="landing__principle-title">{principle.title}</h3>
              <p class="landing__principle-text">{principle.text}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
