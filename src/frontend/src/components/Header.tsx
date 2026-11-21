import { texts } from "../lib/texts";
import { AccessibilityIcon } from "./Icons";

interface HeaderProps {
  onHome: () => void;
  onOpenAccessibility: () => void;
}

export function Header({ onHome, onOpenAccessibility }: HeaderProps) {
  return (
    <header class="border-b border-line bg-page">
      <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-5 sm:px-8">
        <a href="/" onClick={(event) => { event.preventDefault(); onHome(); }} class="text-2xl font-semibold text-ink no-underline">
          {texts.appName}
        </a>
        <nav aria-label={texts.nav.label} class="flex flex-wrap items-center gap-4 sm:gap-8">
          <a
            href="/"
            onClick={(event) => { event.preventDefault(); onHome(); }}
            class="text-lg text-ink underline underline-offset-4"
          >
            {texts.nav.home}
          </a>
          <button
            type="button"
            onClick={onOpenAccessibility}
            class="inline-flex items-center gap-2 rounded-lg border-2 border-ink px-3 py-1.5 text-lg text-ink hover:bg-neutral-soft"
          >
            <AccessibilityIcon class="h-5 w-5" />
            {texts.nav.accessibility}
          </button>
        </nav>
      </div>
    </header>
  );
}
