import { texts } from "../lib/texts";
import "./Header.scss";
import { AccessibilityIcon } from "./Icons";

interface HeaderProps {
  onHome: () => void;
  onOpenAccessibility: () => void;
}

export function Header({ onHome, onOpenAccessibility }: HeaderProps) {
  const goHome = (event: MouseEvent) => {
    event.preventDefault();
    onHome();
  };
  return (
    <header class="header">
      <div class="header__inner">
        <a href="/" onClick={goHome} class="header__brand">
          {texts.appName}
        </a>
        <nav aria-label={texts.nav.label} class="header__nav">
          <a href="/" onClick={goHome} class="header__link">
            {texts.nav.home}
          </a>
          <button type="button" onClick={onOpenAccessibility} class="header__accessibility">
            <AccessibilityIcon class="header__accessibility-icon" />
            {texts.nav.accessibility}
          </button>
        </nav>
      </div>
    </header>
  );
}
