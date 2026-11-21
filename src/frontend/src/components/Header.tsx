import { useEffect, useRef } from "preact/hooks";
import { texts } from "../lib/texts";
import "./Header.scss";
import { AccessibilityIcon } from "./Icons";

// Read by ResultView.scss: the fixed claim drawer starts below the sticky header.
const HEADER_HEIGHT_PROPERTY = "--header-height";

interface HeaderProps {
  onHome: () => void;
  onOpenAccessibility: () => void;
  // Site-wide notice (demo mode) shown as part of the header, so the sticky block and the measured height include it.
  notice: string | null;
}

export function Header({ onHome, onOpenAccessibility, notice }: HeaderProps) {
  const headerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const root = document.documentElement;
    const observer = new ResizeObserver(() => {
      root.style.setProperty(HEADER_HEIGHT_PROPERTY, `${header.offsetHeight}px`);
    });
    observer.observe(header);
    return () => {
      observer.disconnect();
      root.style.removeProperty(HEADER_HEIGHT_PROPERTY);
    };
  }, []);

  return (
    <header ref={headerRef} class="header">
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
      {notice && <p class="demo-banner">{notice}</p>}
    </header>
  );
}
