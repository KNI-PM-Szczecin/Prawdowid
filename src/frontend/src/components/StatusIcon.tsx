import { toneClass, type Tone } from "../lib/presentation";
import { CheckIcon, CrossIcon, QuestionIcon, WarningIcon } from "./Icons";
import "./StatusIcon.scss";

const TONE_ICON: Record<Tone, typeof CheckIcon> = {
  positive: CheckIcon,
  negative: CrossIcon,
  warning: WarningIcon,
  neutral: QuestionIcon,
};

interface StatusIconProps {
  tone: Tone;
  size?: "large" | "small";
}

export function StatusIcon({ tone, size = "large" }: StatusIconProps) {
  const Icon = TONE_ICON[tone];
  if (size === "small") {
    return <Icon class={`status-icon-small ${toneClass(tone)}`} />;
  }
  return (
    <span class={`status-icon ${toneClass(tone)}`} aria-hidden="true">
      <Icon class="status-icon__glyph" />
    </span>
  );
}
