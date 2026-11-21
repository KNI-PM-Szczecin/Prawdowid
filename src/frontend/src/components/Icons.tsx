import type { ComponentChildren } from "preact";

interface IconProps {
  class?: string;
}

function SvgIcon({ class: className = "h-6 w-6", children }: IconProps & { children: ComponentChildren }) {
  return (
    <svg
      class={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const CheckIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </SvgIcon>
);

export const CrossIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M6 6l12 12M18 6L6 18" />
  </SvgIcon>
);

export const WarningIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M12 3.5L2.5 20h19L12 3.5z" />
    <path d="M12 10v4.5M12 17.5v.01" />
  </SvgIcon>
);

export const QuestionIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M9 9a3 3 0 1 1 4.5 2.6c-.9.5-1.5 1.2-1.5 2.4" />
    <path d="M12 18v.01" />
  </SvgIcon>
);

export const InfoIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v6M12 7.5v.01" />
  </SvgIcon>
);

export const LandmarkIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M3 9.5L12 4l9 5.5H3z" />
    <path d="M5.5 10v7M10 10v7M14 10v7M18.5 10v7M3.5 20h17" />
  </SvgIcon>
);

export const AccessibilityIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <circle cx="12" cy="4.5" r="1.5" />
    <path d="M5 8l7 1.5L19 8M12 9.5V14l-3 6M12 14l3 6" />
  </SvgIcon>
);

export const ExternalIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </SvgIcon>
);
