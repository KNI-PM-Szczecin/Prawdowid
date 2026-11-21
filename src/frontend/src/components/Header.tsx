import { texts } from "../lib/texts";
import "./Header.scss";
import { AccessibilityIcon } from "./Icons";

interface HeaderProps {
  onHome: () => void;
  onOpenAccessibility: () => void;
}

export function Header({ onHome, onOpenAccessibility }: HeaderProps) {
  return (
    <header class="header">
      <div class="header__inner">
        <a
          href="/"
          onClick={(event) => {
            event.preventDefault();
            onHome();
          }}
          class="header__brand"
        >
          {texts.appName}
        </a>
        <nav aria-label={texts.nav.label}>
          <button type="button" onClick={onOpenAccessibility} class="header__accessibility">
            <AccessibilityIcon class="header__accessibility-icon" />
            {texts.nav.accessibility}
          </button>
        </nav>
      </div>
    </header>
  );
}
