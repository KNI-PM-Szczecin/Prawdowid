import { TONE_CLASSES, type Tone } from "../lib/presentation";
import { CheckIcon, CrossIcon, QuestionIcon, WarningIcon } from "./Icons";

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
    return <Icon class={`h-5 w-5 shrink-0 ${TONE_CLASSES[tone].icon}`} />;
  }
  return (
    <span
      class={`flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-[10px] border-current bg-page ${TONE_CLASSES[tone].icon}`}
      aria-hidden="true"
    >
      <Icon class="h-9 w-9" />
    </span>
  );
}
